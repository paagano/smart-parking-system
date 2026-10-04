"""
QR Access Token API Endpoints.

Provides operator and mobile-facing endpoints for
temporary QR-based parking access tokens.

QR tokens are facility-scoped and purpose-specific.

ENTRY:
    Used for QR-based parking entry.

EXIT:
    Used for QR-based parking exit.
"""

from __future__ import annotations

import html
from datetime import timedelta
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.dependencies.auth import (
    get_current_active_user,
    require_facility_attendant,
)
from app.api.dependencies.services import (
    ParkingReservationServiceDep,
    PaymentServiceDep,
    QRAccessTokenServiceDep,
    VehicleServiceDep,
    get_parking_session_service,
)
from app.config.settings import settings
from app.utils.datetime import utc_now
from app.models.enums import (
    BillingType,
    EntryMethod,
    ExitMethod,
    VehicleType,
    QRAccessPurpose,
    ReservationStatus,
    SessionSource,
    SessionStatus,
)
from app.models.parking_bay import ParkingBay
from app.models.parking_reservation import ParkingReservation
from app.models.parking_session import ParkingSession
from app.models.parking_zone import ParkingZone
from app.models.user import User
from app.schemas.qr_access_token import (
    QRAccessEntryIdentifyRequest,
    QRAccessEntryIdentifyResponse,
    QRAccessTokenCreate,
    QRAccessTokenDisplayResponse,
    QRAccessTokenResolveRequest,
    QRAccessTokenResolveResponse,
    QRAccessTokenResponse,
)
from app.schemas.parking_session import (
    ParkingSessionCheckout,
    ParkingSessionCreate,
)


router = APIRouter(
    prefix="/qr-access",
    tags=["QR Access"],
)


class QRAccessEntryAuthenticateRequest(BaseModel):
    """Credentials-independent payload used after QR login."""

    token: str = Field(min_length=1)
    registration_number: str = Field(min_length=1)
    vehicle_type: VehicleType | None = None


class QRAccessEntryAuthenticateResponse(BaseModel):
    """Result of authenticated QR entry."""

    valid: bool
    facility_id: int
    vehicle_id: int | None
    registration_number: str
    authenticated_user_id: int | None = None
    reservation_id: int | None = None
    session_id: int
    session_number: str
    session_source: SessionSource
    entry_method: EntryMethod
    message: str


CurrentFacilityAttendantDep = Annotated[
    User,
    Depends(require_facility_attendant),
]


def _require_facility(
    current_user: CurrentFacilityAttendantDep,
) -> int:
    """
    Return the authenticated user's facility ID.

    QR access is facility-scoped and therefore requires
    the authenticated user to be assigned to a facility.
    """

    facility_id = getattr(
        current_user,
        "facility_id",
        None,
    )

    if facility_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Authenticated user is not assigned "
                "to a facility."
            ),
        )

    return facility_id


async def _complete_qr_entry(
    *,
    data: QRAccessEntryAuthenticateRequest,
    current_user_id: int | None,
    qr_service: QRAccessTokenServiceDep,
    vehicle_service: VehicleServiceDep,
    reservation_service: ParkingReservationServiceDep,
    parking_session_service,
) -> QRAccessEntryAuthenticateResponse:
    """Complete QR entry for an authenticated or guest driver.

    ``current_user_id`` is the customer who will be responsible for
    the parking session payment when a registered SmartPark driver
    is authenticated. For a guest driver using a registered vehicle,
    the registered vehicle owner remains the payment customer.
    """

    try:
        qr_access_token = await qr_service.resolve_public_token(
            raw_token=data.token,
            purpose=QRAccessPurpose.ENTRY,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    normalized_registration = "".join(
        data.registration_number.split()
    ).upper()

    vehicle = None

    try:
        vehicle = await vehicle_service.get_by_registration_number(
            registration_number=normalized_registration,
        )
    except ValueError:
        # An unknown registration is a valid QR guest drive-in case.
        # Continue without a registered Vehicle record.
        vehicle = None

    if vehicle is not None and not vehicle.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This vehicle is currently inactive.",
        )

    if vehicle is None and data.vehicle_type is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Vehicle type is required for an unregistered vehicle.",
        )

    now = utc_now()

    active_reservations = (
        await reservation_service.get_active_by_vehicle(
            vehicle.registration_number,
        )
        if vehicle is not None
        else []
    )

    applicable_reservations = [
        reservation
        for reservation in active_reservations
        if reservation.vehicle_id == vehicle.id
        and reservation.status in (
            ReservationStatus.CREATED,
            ReservationStatus.CONFIRMED,
        )
        and now >= reservation.reserved_from - timedelta(minutes=30)
        and now < reservation.reserved_until
    ]

    if len(applicable_reservations) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Multiple active reservations were found for this vehicle. "
                "The reservation conflict must be resolved before QR entry."
            ),
        )

    reservation = (
        applicable_reservations[0]
        if applicable_reservations
        else None
    )

    if reservation is not None:
        reservation_facility_id = await (
            parking_session_service
            .parking_bay_repository
            .get_facility_id(reservation.parking_bay_id)
        )

        if reservation_facility_id != qr_access_token.facility_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "The reservation belongs to a different parking facility "
                    "than this QR access point."
                ),
            )

        try:
            parking_session = await (
                parking_session_service.create_from_reservation(
                    reservation,
                    entry_method=EntryMethod.QR_CODE,
                )
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        # The reservation remains owned by its reservation customer,
        # but the active parking session is charged to the person
        # actually using the vehicle when that person is authenticated.
        # A guest driver falls back to the registered vehicle owner.
        parking_session.customer_id = (
            current_user_id
            if current_user_id is not None
            else vehicle.customer_id
        )
        await parking_session_service.repository.save(parking_session)
        await parking_session_service.repository.db.commit()
        await parking_session_service.repository.db.refresh(parking_session)

        reservation.status = ReservationStatus.CHECKED_IN
        reservation.checked_in_at = now
        reservation.updated_at = now

        await reservation_service.repository.save(reservation)
        await reservation_service.repository.commit()
        await reservation_service.repository.refresh(reservation)

        if current_user_id is None:
            message = (
                "Guest driver accepted. Reservation check-in completed "
                "successfully. The registered vehicle owner is the default "
                "wallet payer; M-Pesa or Cash can also be used at checkout."
            )
        else:
            message = (
                "Driver authenticated and reservation check-in completed "
                "successfully. The authenticated driver is the parking "
                "session payer."
            )

        return QRAccessEntryAuthenticateResponse(
            valid=True,
            facility_id=qr_access_token.facility_id,
            vehicle_id=vehicle.id,
            registration_number=vehicle.registration_number,
            authenticated_user_id=current_user_id,
            reservation_id=reservation.id,
            session_id=parking_session.id,
            session_number=parking_session.session_number,
            session_source=parking_session.session_source,
            entry_method=parking_session.entry_method,
            message=message,
        )

    # ----------------------------------------------------------
    # DRIVE_IN QR entry.
    # ----------------------------------------------------------

    available_bay_query = (
        select(ParkingBay)
        .join(ParkingZone, ParkingZone.id == ParkingBay.zone_id)
        .where(
            ParkingZone.facility_id == qr_access_token.facility_id,
            ParkingZone.is_active.is_(True),
            ParkingBay.is_active.is_(True),
            ParkingBay.is_reservable.is_(True),
            ~select(ParkingSession.id)
            .where(
                ParkingSession.parking_bay_id == ParkingBay.id,
                ParkingSession.status == SessionStatus.ACTIVE,
            )
            .exists(),
            ~select(ParkingReservation.id)
            .where(
                ParkingReservation.parking_bay_id == ParkingBay.id,
                ParkingReservation.status.in_(
                    (
                        ReservationStatus.CREATED,
                        ReservationStatus.CONFIRMED,
                    )
                ),
                ParkingReservation.reserved_from < now,
                ParkingReservation.reserved_until > now,
            )
            .exists(),
        )
        .order_by(ParkingBay.sort_order, ParkingBay.bay_number)
        .limit(1)
    )

    available_bay_result = await parking_session_service.repository.db.execute(
        available_bay_query
    )
    available_bay = available_bay_result.scalar_one_or_none()

    if available_bay is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No available parking bay is currently available at this facility.",
        )

    # Authenticated drivers pay from their own wallet. A guest using a
    # registered vehicle defaults the session payer to the vehicle owner.
    # An unregistered QR guest has no customer account, so the session
    # customer remains unset and payment can use the existing checkout
    # M-Pesa/Cash flow.
    session_customer_id = (
        current_user_id
        if current_user_id is not None
        else (vehicle.customer_id if vehicle is not None else None)
    )

    parking_session_data = ParkingSessionCreate(
        parking_bay_id=available_bay.id,
        customer_id=session_customer_id,
        vehicle_id=vehicle.id if vehicle is not None else None,
        vehicle_registration=(
            None if vehicle is not None else normalized_registration
        ),
        vehicle_type=(
            None if vehicle is not None else data.vehicle_type
        ),
        billing_type=BillingType.HOURLY,
        session_source=SessionSource.DRIVE_IN,
        entry_method=EntryMethod.QR_CODE,
    )

    try:
        parking_session = await parking_session_service.check_in_vehicle(
            parking_session_data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if vehicle is None:
        message = (
            "Guest vehicle checked in successfully as a drive-in customer. "
            "M-Pesa or Cash can be used at checkout."
        )
    elif current_user_id is None:
        message = (
            "Guest driver accepted and vehicle checked in successfully as a "
            "drive-in customer. The registered vehicle owner is the default "
            "wallet payer; M-Pesa or Cash can also be used at checkout."
        )
    else:
        message = (
            "Driver authenticated and vehicle checked in successfully as a "
            "drive-in customer. The authenticated driver is the parking "
            "session payer."
        )

    return QRAccessEntryAuthenticateResponse(
        valid=True,
        facility_id=qr_access_token.facility_id,
        vehicle_id=vehicle.id if vehicle is not None else None,
        registration_number=(
            vehicle.registration_number
            if vehicle is not None
            else normalized_registration
        ),
        authenticated_user_id=current_user_id,
        reservation_id=None,
        session_id=parking_session.id,
        session_number=parking_session.session_number,
        session_source=parking_session.session_source,
        entry_method=parking_session.entry_method,
        message=message,
    )


@router.post(
    "/entry/authenticate",
    response_model=QRAccessEntryAuthenticateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def authenticate_qr_entry(
    data: QRAccessEntryAuthenticateRequest,
    current_user: User = Depends(get_current_active_user),
    qr_service: QRAccessTokenServiceDep = None,
    vehicle_service: VehicleServiceDep = None,
    reservation_service: ParkingReservationServiceDep = None,
    parking_session_service=Depends(get_parking_session_service),
) -> QRAccessEntryAuthenticateResponse:
    """
    Complete QR entry for an authenticated SmartPark driver.

    The authenticated driver does not need to be the registered vehicle
    owner. When a customer borrows another registered vehicle, the active
    parking session is assigned to the authenticated driver so that the
    driver's wallet is used for automatic wallet checkout.
    """

    return await _complete_qr_entry(
        data=data,
        current_user_id=current_user.id,
        qr_service=qr_service,
        vehicle_service=vehicle_service,
        reservation_service=reservation_service,
        parking_session_service=parking_session_service,
    )


@router.post(
    "/entry/guest",
    response_model=QRAccessEntryAuthenticateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def guest_qr_entry(
    data: QRAccessEntryAuthenticateRequest,
    qr_service: QRAccessTokenServiceDep = None,
    vehicle_service: VehicleServiceDep = None,
    reservation_service: ParkingReservationServiceDep = None,
    parking_session_service=Depends(get_parking_session_service),
) -> QRAccessEntryAuthenticateResponse:
    """
    Complete QR entry for an unauthenticated/guest driver using a
    registered vehicle.

    The registered vehicle owner remains the default payment customer.
    The operator can still use the existing M-Pesa or Cash payment
    options at checkout when the person actually driving the vehicle
    should pay instead.
    """

    return await _complete_qr_entry(
        data=data,
        current_user_id=None,
        qr_service=qr_service,
        vehicle_service=vehicle_service,
        reservation_service=reservation_service,
        parking_session_service=parking_session_service,
    )


@router.post(
    "/tokens",
    response_model=QRAccessTokenDisplayResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_qr_access_token(
    data: QRAccessTokenCreate,
    current_user: CurrentFacilityAttendantDep,
    service: QRAccessTokenServiceDep,
) -> QRAccessTokenDisplayResponse:
    """
    Generate a temporary QR access token for the
    authenticated user's facility.

    The raw token is returned only during creation.
    """

    facility_id = _require_facility(current_user)

    qr_access_token, raw_token = await service.create_token(
        facility_id=facility_id,
        purpose=data.purpose,
        expires_in_seconds=data.expires_in_seconds,
    )

    # ----------------------------------------------------------
    # PURPOSE-AWARE PUBLIC QR URL
    # ----------------------------------------------------------
    #
    # ENTRY tokens must open:
    #
    #     /qr-access/entry
    #
    # EXIT tokens must open:
    #
    #     /qr-access/exit
    #
    # The public base URL is the same configured URL already
    # used by SmartPark receipt QR verification.
    # ----------------------------------------------------------

    qr_access_path = (
        "/qr-access/entry"
        if data.purpose == QRAccessPurpose.ENTRY
        else "/qr-access/exit"
    )

    qr_url = (
        f"{settings.RECEIPT_VERIFICATION_BASE_URL.rstrip('/')}"
        f"{qr_access_path}?token={raw_token}"
    )

    return QRAccessTokenDisplayResponse(
        id=qr_access_token.id,
        facility_id=qr_access_token.facility_id,
        purpose=qr_access_token.purpose,
        expires_at=qr_access_token.expires_at,
        is_active=qr_access_token.is_active,
        created_at=qr_access_token.created_at,
        updated_at=qr_access_token.updated_at,
        raw_token=raw_token,
        qr_url=qr_url,
    )


@router.get(
    "/entry",
    response_class=HTMLResponse,
)
async def qr_access_entry_page(
    token: str,
    qr_service: QRAccessTokenServiceDep,
) -> HTMLResponse:
    """
    Render the mobile QR parking-entry page.

    The opaque QR token is validated before the page is
    displayed.

    The token is then retained by the page and submitted
    to the existing /entry/identify endpoint when the
    driver enters the vehicle registration number.
    """

    try:
        qr_access_token = await qr_service.resolve_public_token(
            raw_token=token,
            purpose=QRAccessPurpose.ENTRY,
        )
    except ValueError as exc:
        error_message = html.escape(str(exc))

        return HTMLResponse(
            content=f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >
    <title>SmartPark AI - QR Access</title>
    <style>
        body {{
            margin: 0;
            padding: 24px;
            font-family: Arial, sans-serif;
            background: #f5f7fa;
            color: #1f2937;
        }}

        .container {{
            max-width: 480px;
            margin: 40px auto;
            background: white;
            padding: 28px;
            border-radius: 16px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
        }}

        h1 {{
            margin-top: 0;
            font-size: 24px;
        }}

        .error {{
            margin-top: 20px;
            padding: 14px;
            border-radius: 10px;
            background: #fee2e2;
            color: #991b1b;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>SmartPark AI</h1>
        <p>QR parking access is unavailable.</p>
        <div class="error">{error_message}</div>
    </div>
</body>
</html>
""",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    safe_token = html.escape(token, quote=True)

    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >
    <meta
        name="theme-color"
        content="#0f766e"
    >
    <title>SmartPark AI - Parking Access</title>

    <style>
        * {{
            box-sizing: border-box;
        }}

        body {{
            margin: 0;
            min-height: 100vh;
            padding: 20px;
            font-family:
                Arial,
                Helvetica,
                sans-serif;
            background: #f5f7fa;
            color: #1f2937;
        }}

        .container {{
            width: 100%;
            max-width: 480px;
            margin: 30px auto;
        }}

        .card {{
            background: #ffffff;
            border-radius: 18px;
            padding: 28px 22px;
            box-shadow:
                0 6px 24px rgba(0, 0, 0, 0.08);
        }}

        .logo {{
            text-align: center;
            font-size: 28px;
            font-weight: 700;
            color: #0f766e;
            margin-bottom: 8px;
        }}

        .subtitle {{
            text-align: center;
            color: #6b7280;
            margin-bottom: 28px;
        }}

        label {{
            display: block;
            font-weight: 600;
            margin-bottom: 8px;
        }}

        input {{
            width: 100%;
            padding: 15px;
            border: 1px solid #d1d5db;
            border-radius: 10px;
            font-size: 18px;
            text-transform: uppercase;
            outline: none;
        }}

        input:focus {{
            border-color: #0f766e;
            box-shadow:
                0 0 0 3px rgba(15, 118, 110, 0.12);
        }}

        button {{
            width: 100%;
            margin-top: 18px;
            padding: 15px;
            border: none;
            border-radius: 10px;
            background: #0f766e;
            color: white;
            font-size: 17px;
            font-weight: 600;
            cursor: pointer;
        }}

        button:disabled {{
            opacity: 0.6;
            cursor: not-allowed;
        }}

        .message {{
            display: none;
            margin-top: 20px;
            padding: 15px;
            border-radius: 10px;
            line-height: 1.5;
        }}

        .success {{
            display: block;
            background: #dcfce7;
            color: #166534;
        }}

        .info {{
            display: block;
            background: #dbeafe;
            color: #1e40af;
        }}

        .error {{
            display: block;
            background: #fee2e2;
            color: #991b1b;
        }}

        .payment-section {{
            display: none;
            margin-top: 22px;
            padding-top: 20px;
            border-top: 1px solid #e5e7eb;
        }}

        .payment-title {{
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 8px;
        }}

        .payment-form {{
            display: none;
        }}

        .payment-help {{
            color: #6b7280;
            font-size: 14px;
            line-height: 1.5;
            margin-bottom: 12px;
        }}

        .payment-input {{
            width: 100%;
            padding: 15px;
            border: 1px solid #d1d5db;
            border-radius: 10px;
            font-size: 18px;
            outline: none;
        }}

        .payment-input:focus {{
            border-color: #b45309;
            box-shadow:
                0 0 0 3px rgba(180, 83, 9, 0.12);
        }}

        .payment-button {{
            margin-top: 12px;
            background: #047857;
        }}

        .facility {{
            text-align: center;
            margin-top: 18px;
            font-size: 13px;
            color: #9ca3af;
        }}
    </style>
</head>

<body>
    <div class="container">
        <div class="card">
            <div class="logo">
                SmartPark AI
            </div>

            <div class="subtitle">
                Parking Access
            </div>

            <form id="entryForm">
                <label for="registration">
                    Vehicle Registration Number
                </label>

                <input
                    id="registration"
                    name="registration"
                    type="text"
                    placeholder="e.g. KDA 123A"
                    autocomplete="off"
                    autocapitalize="characters"
                    required
                />

                <div
                    id="vehicleTypeSection"
                    style="display:none; margin-top:16px;"
                >
                    <label for="vehicleType">
                        Vehicle Type
                    </label>

                    <select
                        id="vehicleType"
                        name="vehicleType"
                        style="width:100%;"
                    >
                        <option value="">Select vehicle type</option>
                        <option value="CAR">Car</option>
                        <option value="SUV">SUV</option>
                        <option value="TRUCK">Truck</option>
                        <option value="MOTORCYCLE">Motorcycle</option>
                        <option value="BUS">Bus</option>
                    </select>
                </div>

                <button
                    id="continueButton"
                    type="submit"
                >
                    Continue
                </button>
            </form>

            <div
                id="message"
                class="message"
            ></div>

            <div
                id="paymentSection"
                class="payment-section"
            >
                <div class="payment-title">Payment Required</div>

                <button
                    id="makePaymentButton"
                    type="button"
                >
                    Make Payment
                </button>

                <div
                    id="paymentForm"
                    class="payment-form"
                >
                    <div class="payment-help">
                        Enter the Safaricom M-Pesa number that should receive
                        the payment prompt, then tap Complete Payment.
                    </div>

                    <input
                        id="mpesaNumber"
                        class="payment-input"
                        type="tel"
                        inputmode="numeric"
                        autocomplete="tel"
                        placeholder="e.g. 0712345678"
                    />

                    <button
                        id="completePaymentButton"
                        class="payment-button"
                        type="button"
                    >
                        Complete Payment
                    </button>
                </div>
            </div>

            <div class="facility">
                Secure SmartPark AI QR Access
            </div>
        </div>
    </div>

    <script>
        const token = "{safe_token}";

        const form =
            document.getElementById("entryForm");

        const registrationInput =
            document.getElementById("registration");

        const continueButton =
            document.getElementById("continueButton");

        const vehicleTypeSection =
            document.getElementById("vehicleTypeSection");

        const vehicleTypeInput =
            document.getElementById("vehicleType");

        const message =
            document.getElementById("message");

        const paymentSection =
            document.getElementById("paymentSection");

        const makePaymentButton =
            document.getElementById("makePaymentButton");

        const paymentForm =
            document.getElementById("paymentForm");

        const mpesaNumber =
            document.getElementById("mpesaNumber");

        const completePaymentButton =
            document.getElementById("completePaymentButton");

        const proceedToExitButton =
            document.getElementById("proceedToExitButton");

        let identifiedRegistration = "";
        let guestEntryMode = false;

        function showMessage(text, type) {{
            message.textContent = text;
            message.className =
                "message " + type;
        }}

        function showAuthenticationForm() {{
            message.className = "message info";
            message.innerHTML = `
                <div style="font-weight:600;margin-bottom:12px;">
                    Registered vehicle identified
                </div>
                <div style="margin-bottom:14px;line-height:1.5;">
                    You can sign in so your own SmartPark wallet is used for parking charges, or continue as a guest.
                </div>
                <form id="authenticationForm">
                    <label for="email" style="color:#1f2937;">Email address</label>
                    <input id="email" type="email" autocomplete="username" required style="margin-top:8px;text-transform:none;background:#fff;" />
                    <label for="password" style="color:#1f2937;margin-top:14px;">Password</label>
                    <input id="password" type="password" autocomplete="current-password" required style="margin-top:8px;text-transform:none;background:#fff;" />
                    <button id="authenticateButton" type="submit" style="margin-top:16px;">
                        Sign In & Continue
                    </button>
                </form>
                <button
                    id="guestButton"
                    type="button"
                    style="margin-top:10px;background:#475569;"
                >
                    Continue as Guest
                </button>
            `;

            const authenticationForm =
                document.getElementById("authenticationForm");
            const guestButton =
                document.getElementById("guestButton");

            guestButton.addEventListener(
                "click",
                async function() {{
                    guestButton.disabled = true;
                    guestButton.textContent = "Checking In...";
                    await completeGuestEntry(guestButton);
                }}
            );

            authenticationForm.addEventListener(
                "submit",
                async function(authenticationEvent) {{
                    authenticationEvent.preventDefault();

                    const email =
                        document.getElementById("email").value.trim();
                    const password =
                        document.getElementById("password").value;
                    const authenticateButton =
                        document.getElementById("authenticateButton");

                    authenticateButton.disabled = true;
                    authenticateButton.textContent = "Authenticating...";

                    try {{
                        const loginForm = new URLSearchParams();
                        loginForm.append("username", email);
                        loginForm.append("password", password);

                        const loginResponse = await fetch(
                            "/auth/login",
                            {{
                                method: "POST",
                                headers: {{
                                    "Content-Type":
                                        "application/x-www-form-urlencoded"
                                }},
                                body: loginForm.toString()
                            }}
                        );

                        const loginData = await loginResponse.json();

                        if (!loginResponse.ok) {{
                            throw new Error(
                                loginData.detail ||
                                "Authentication failed."
                            );
                        }}

                        const accessToken = loginData.access_token;

                        const entryResponse = await fetch(
                            "/qr-access/entry/authenticate",
                            {{
                                method: "POST",
                                headers: {{
                                    "Content-Type": "application/json",
                                    "Authorization":
                                        "Bearer " + accessToken
                                }},
                                body: JSON.stringify({{
                                    token: token,
                                    registration_number:
                                        registrationInput.value.trim()
                                }})
                            }}
                        );

                        const entryData = await entryResponse.json();

                        if (!entryResponse.ok) {{
                            throw new Error(
                                entryData.detail ||
                                "Unable to complete QR parking entry."
                            );
                        }}

                        message.className = "message success";
                        message.textContent = entryData.message;
                        authenticationForm.remove();
                        guestButton.remove();
                        continueButton.style.display = "none";
                        registrationInput.disabled = true;
                    }} catch (error) {{
                        message.className = "message error";
                        message.textContent =
                            error.message ||
                            "Unable to authenticate the driver.";
                    }} finally {{
                        authenticateButton.disabled = false;
                        authenticateButton.textContent =
                            "Sign In & Continue";
                    }}
                }}
            );
        }}

        async function completeGuestEntry(guestButton) {{
            const vehicleType =
                vehicleTypeInput.value;

            if (!vehicleType) {{
                showMessage(
                    "Please select the vehicle type before continuing as a guest.",
                    "error"
                );
                guestButton.disabled = false;
                guestButton.textContent = "Continue as Guest";
                return;
            }}

            try {{
                const response = await fetch(
                    "/qr-access/entry/guest",
                    {{
                        method: "POST",
                        headers: {{
                            "Content-Type": "application/json"
                        }},
                        body: JSON.stringify({{
                            token: token,
                            registration_number:
                                registrationInput.value.trim(),
                            vehicle_type:
                                vehicleTypeInput.value
                        }})
                    }}
                );

                const data = await response.json();

                if (!response.ok) {{
                    throw new Error(
                        data.detail ||
                        "Unable to complete guest QR parking entry."
                    );
                }}

                message.className = "message success";
                message.textContent = data.message;
                guestButton.remove();
                continueButton.style.display = "none";
                registrationInput.disabled = true;
            }} catch (error) {{
                message.className = "message error";
                message.textContent =
                    error.message ||
                    "Unable to complete guest parking entry.";
                guestButton.disabled = false;
                guestButton.textContent = "Continue as Guest";
            }}
        }}


        form.addEventListener(
            "submit",
            async function(event) {{
                event.preventDefault();

                const registration =
                    registrationInput.value
                        .trim()
                        .toUpperCase();

                if (guestEntryMode) {{
                    continueButton.disabled = true;
                    continueButton.textContent =
                        "Checking In...";
                    await completeGuestEntry(continueButton);
                    return;
                }}

                if (!registration) {{
                    showMessage(
                        "Please enter your vehicle registration number.",
                        "error"
                    );
                    return;
                }}

                continueButton.disabled = true;
                continueButton.textContent =
                    "Checking...";

                message.className = "message";
                message.textContent = "";

                try {{
                    const response =
                        await fetch(
                            "/qr-access/entry/identify",
                            {{
                                method: "POST",
                                headers: {{
                                    "Content-Type":
                                        "application/json"
                                }},
                                body: JSON.stringify({{
                                    token: token,
                                    registration_number:
                                        registration
                                }})
                            }}
                        );

                    const data =
                        await response.json();

                    if (!response.ok) {{
                        throw new Error(
                            data.detail ||
                            "Unable to validate QR access."
                        );
                    }}

                    if (data.registered) {{
                        guestEntryMode = false;
                        vehicleTypeSection.style.display = "none";
                        vehicleTypeInput.value = "";

                        if (!data.vehicle_active) {{
                            showMessage(
                                "This vehicle is registered but is currently inactive.",
                                "error"
                            );
                        }} else {{
                            showAuthenticationForm();
                        }}
                    }} else {{
                        guestEntryMode = true;
                        vehicleTypeSection.style.display = "block";
                        vehicleTypeInput.value = "";
                        showMessage(
                            data.message +
                            " Please select your vehicle type before continuing.",
                            "info"
                        );
                        continueButton.textContent =
                            "Continue as Guest";
                    }}
                }} catch (error) {{
                    showMessage(
                        error.message ||
                        "Unable to process the request.",
                        "error"
                    );
                }} finally {{
                    continueButton.disabled = false;
                    continueButton.textContent = guestEntryMode
                        ? "Continue as Guest"
                        : "Continue";
                }}
            }}
        );
    </script>
</body>
</html>
"""

    return HTMLResponse(
        content=html_content,
        status_code=status.HTTP_200_OK,
    )



@router.get(
    "/exit",
    response_class=HTMLResponse,
)
async def qr_access_exit_page(
    token: str,
    qr_service: QRAccessTokenServiceDep,
) -> HTMLResponse:
    """
    Render the mobile QR parking-exit page.

    The opaque QR token is validated before the page is
    displayed. The token is retained by the page and used
    to identify the parking session when the driver enters
    the vehicle registration number.
    """

    try:
        qr_access_token = await qr_service.resolve_public_token(
            raw_token=token,
            purpose=QRAccessPurpose.EXIT,
        )
    except ValueError as exc:
        error_message = html.escape(str(exc))

        return HTMLResponse(
            content=f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >
    <title>SmartPark AI - QR Exit</title>
    <style>
        body {{
            margin: 0;
            padding: 24px;
            font-family: Arial, sans-serif;
            background: #f5f7fa;
            color: #1f2937;
        }}

        .container {{
            max-width: 480px;
            margin: 40px auto;
            background: white;
            padding: 28px;
            border-radius: 16px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
        }}

        h1 {{
            margin-top: 0;
            font-size: 24px;
        }}

        .error {{
            margin-top: 20px;
            padding: 14px;
            border-radius: 10px;
            background: #fee2e2;
            color: #991b1b;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>SmartPark AI</h1>
        <p>QR parking exit is unavailable.</p>
        <div class="error">{error_message}</div>
    </div>
</body>
</html>
""",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    safe_token = html.escape(token, quote=True)

    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >
    <meta
        name="theme-color"
        content="#b45309"
    >
    <title>SmartPark AI - Parking Exit</title>

    <style>
        * {{
            box-sizing: border-box;
        }}

        body {{
            margin: 0;
            min-height: 100vh;
            padding: 20px;
            font-family:
                Arial,
                Helvetica,
                sans-serif;
            background: #f5f7fa;
            color: #1f2937;
        }}

        .container {{
            width: 100%;
            max-width: 480px;
            margin: 30px auto;
        }}

        .card {{
            background: #ffffff;
            border-radius: 18px;
            padding: 28px 22px;
            box-shadow:
                0 6px 24px rgba(0, 0, 0, 0.08);
        }}

        .logo {{
            text-align: center;
            font-size: 28px;
            font-weight: 700;
            color: #b45309;
            margin-bottom: 8px;
        }}

        .subtitle {{
            text-align: center;
            color: #6b7280;
            margin-bottom: 28px;
        }}

        label {{
            display: block;
            font-weight: 600;
            margin-bottom: 8px;
        }}

        input {{
            width: 100%;
            padding: 15px;
            border: 1px solid #d1d5db;
            border-radius: 10px;
            font-size: 18px;
            text-transform: uppercase;
            outline: none;
        }}

        input:focus {{
            border-color: #b45309;
            box-shadow:
                0 0 0 3px rgba(180, 83, 9, 0.12);
        }}

        button {{
            width: 100%;
            margin-top: 18px;
            padding: 15px;
            border: none;
            border-radius: 10px;
            background: #b45309;
            color: white;
            font-size: 17px;
            font-weight: 600;
            cursor: pointer;
        }}

        button:disabled {{
            opacity: 0.6;
            cursor: not-allowed;
        }}

        .message {{
            display: none;
            margin-top: 20px;
            padding: 15px;
            border-radius: 10px;
            line-height: 1.5;
        }}

        .success {{
            display: block;
            background: #dcfce7;
            color: #166534;
        }}

        .info {{
            display: block;
            background: #dbeafe;
            color: #1e40af;
        }}

        .error {{
            display: block;
            background: #fee2e2;
            color: #991b1b;
        }}

        .payment-section {{
            display: none;
            margin-top: 22px;
            padding-top: 20px;
            border-top: 1px solid #e5e7eb;
        }}

        .payment-title {{
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 8px;
        }}

        .payment-form {{
            display: none;
        }}

        .payment-help {{
            color: #6b7280;
            font-size: 14px;
            line-height: 1.5;
            margin-bottom: 12px;
        }}

        .payment-input {{
            width: 100%;
            padding: 15px;
            border: 1px solid #d1d5db;
            border-radius: 10px;
            font-size: 18px;
            outline: none;
        }}

        .payment-input:focus {{
            border-color: #b45309;
            box-shadow:
                0 0 0 3px rgba(180, 83, 9, 0.12);
        }}

        .payment-button {{
            margin-top: 12px;
            background: #047857;
        }}

        .facility {{
            text-align: center;
            margin-top: 18px;
            font-size: 13px;
            color: #9ca3af;
        }}
    </style>
</head>

<body>
    <div class="container">
        <div class="card">
            <div class="logo">
                SmartPark AI
            </div>

            <div class="subtitle">
                Parking Exit
            </div>

            <form id="exitForm">
                <label for="registration">
                    Vehicle Registration Number
                </label>

                <input
                    id="registration"
                    name="registration"
                    type="text"
                    placeholder="e.g. KDA 123A"
                    autocomplete="off"
                    autocapitalize="characters"
                    required
                />

                <button
                    id="continueButton"
                    type="submit"
                >
                    Check Parking Status
                </button>
            </form>

            <div
                id="message"
                class="message"
            ></div>

            <div
                id="paymentSection"
                class="payment-section"
            >
                <div class="payment-title">Payment Required</div>

                <button
                    id="makePaymentButton"
                    type="button"
                >
                    Make Payment
                </button>

                <div
                    id="paymentForm"
                    class="payment-form"
                >
                    <div class="payment-help">
                        Enter the Safaricom M-Pesa number that should receive
                        the payment prompt, then tap Complete Payment.
                    </div>

                    <input
                        id="mpesaNumber"
                        class="payment-input"
                        type="tel"
                        inputmode="numeric"
                        autocomplete="tel"
                        placeholder="e.g. 0712345678"
                    />

                    <button
                        id="completePaymentButton"
                        class="payment-button"
                        type="button"
                    >
                        Complete Payment
                    </button>
                </div>
            </div>

            <button
                id="proceedToExitButton"
                class="payment-button"
                type="button"
                style="display:none;"
            >
                Proceed to Exit
            </button>

            <div class="facility">
                Secure SmartPark AI QR Exit
            </div>
        </div>
    </div>

    <script>
        const token = "{safe_token}";

        const form =
            document.getElementById("exitForm");

        const registrationInput =
            document.getElementById("registration");

        const continueButton =
            document.getElementById("continueButton");

        const message =
            document.getElementById("message");

        const paymentSection =
            document.getElementById("paymentSection");

        const makePaymentButton =
            document.getElementById("makePaymentButton");

        const paymentForm =
            document.getElementById("paymentForm");

        const mpesaNumber =
            document.getElementById("mpesaNumber");

        const completePaymentButton =
            document.getElementById("completePaymentButton");

        let identifiedRegistration = "";

        function showMessage(text, type) {{
            message.textContent = text;
            message.className =
                "message " + type;
        }}

        form.addEventListener(
            "submit",
            async function(event) {{
                event.preventDefault();

                const registration =
                    registrationInput.value
                        .trim()
                        .toUpperCase();

                if (!registration) {{
                    showMessage(
                        "Please enter your vehicle registration number.",
                        "error"
                    );
                    return;
                }}

                continueButton.disabled = true;
                continueButton.textContent =
                    "Checking...";
                message.className = "message";
                message.textContent = "";

                try {{
                    const response = await fetch(
                        "/qr-access/exit/identify",
                        {{
                            method: "POST",
                            headers: {{
                                "Content-Type":
                                    "application/json"
                            }},
                            body: JSON.stringify({{
                                token: token,
                                registration_number: registration
                            }})
                        }}
                    );

                    const data = await response.json();

                    if (!response.ok) {{
                        throw new Error(
                            data.detail ||
                            "Unable to identify the parking session."
                        );
                    }}

                    showMessage(
                        data.message,
                        data.payment_required ? "info" : "success"
                    );

                    identifiedRegistration = registration;
                    registrationInput.disabled = true;
                    continueButton.style.display = "none";

                    if (data.payment_required) {{
                        paymentSection.style.display = "block";
                        paymentForm.style.display = "none";
                        makePaymentButton.style.display = "block";
                        proceedToExitButton.style.display = "none";
                    }} else {{
                        paymentSection.style.display = "none";
                        proceedToExitButton.style.display = "block";
                    }}
                }} catch (error) {{
                    showMessage(
                        error.message ||
                        "Unable to process the QR parking exit request.",
                        "error"
                    );
                }} finally {{
                    continueButton.disabled = false;
                    continueButton.textContent =
                        "Check Parking Status";
                }}
            }}
        );
        makePaymentButton.addEventListener(
            "click",
            function() {{
                makePaymentButton.style.display = "none";
                paymentForm.style.display = "block";
                mpesaNumber.focus();
            }}
        );

        proceedToExitButton.addEventListener(
            "click",
            async function() {{
                proceedToExitButton.disabled = true;
                proceedToExitButton.textContent = "Processing Exit...";

                try {{
                    const response = await fetch(
                        "/qr-access/exit/checkout",
                        {{
                            method: "POST",
                            headers: {{
                                "Content-Type":
                                    "application/json"
                            }},
                            body: JSON.stringify({{
                                token: token,
                                registration_number:
                                    identifiedRegistration
                            }})
                        }}
                    );

                    const data = await response.json();

                    if (!response.ok) {{
                        throw new Error(
                            data.detail ||
                            "Unable to complete the physical vehicle exit."
                        );
                    }}

                    showMessage(
                        data.message ||
                        "Vehicle exited successfully.",
                        "success"
                    );

                    proceedToExitButton.style.display = "none";
                    registrationInput.disabled = true;
                }} catch (error) {{
                    showMessage(
                        error.message ||
                        "Unable to complete the physical vehicle exit.",
                        "error"
                    );
                    proceedToExitButton.disabled = false;
                    proceedToExitButton.textContent =
                        "Proceed to Exit";
                }}
            }}
        );

        completePaymentButton.addEventListener(
            "click",
            async function() {{
                const phone = mpesaNumber.value.trim();

                if (!phone) {{
                    showMessage(
                        "Enter the Safaricom M-Pesa number to receive the payment prompt.",
                        "error"
                    );
                    mpesaNumber.focus();
                    return;
                }}

                completePaymentButton.disabled = true;
                completePaymentButton.textContent =
                    "Sending M-Pesa Prompt...";

                try {{
                    const response = await fetch(
                        "/qr-access/exit/payment/stk-push",
                        {{
                            method: "POST",
                            headers: {{
                                "Content-Type":
                                    "application/json"
                            }},
                            body: JSON.stringify({{
                                token: token,
                                registration_number:
                                    identifiedRegistration,
                                mobile_number: phone
                            }})
                        }}
                    );

                    const data = await response.json();

                    if (!response.ok) {{
                        throw new Error(
                            data.detail ||
                            "Unable to initiate the M-Pesa payment."
                        );
                    }}

                    showMessage(
                        `M-Pesa prompt sent to ${{data.phone_number}}. ` +
                        "Enter your M-Pesa PIN on your phone to complete the payment.",
                        "success"
                    );

                    completePaymentButton.disabled = true;
                    completePaymentButton.textContent =
                        "M-Pesa Prompt Sent";
                    mpesaNumber.disabled = true;
                }} catch (error) {{
                    showMessage(
                        error.message ||
                        "Unable to initiate the M-Pesa payment.",
                        "error"
                    );
                    completePaymentButton.disabled = false;
                    completePaymentButton.textContent =
                        "Complete Payment";
                }}
            }}
        );

    </script>
</body>
</html>
"""

    return HTMLResponse(
        content=html_content,
        status_code=status.HTTP_200_OK,
    )


class QRAccessExitIdentifyRequest(BaseModel):
    """Vehicle identification payload used by the QR exit page."""

    token: str = Field(min_length=1)
    registration_number: str = Field(min_length=1)


class QRAccessExitPaymentRequest(BaseModel):
    """M-Pesa payment payload used by the public QR exit page."""

    token: str = Field(min_length=1)
    registration_number: str = Field(min_length=1)
    mobile_number: str = Field(min_length=9, max_length=20)


class QRAccessExitPaymentResponse(BaseModel):
    """Result returned after an M-Pesa STK Push is initiated."""

    valid: bool
    parking_session_id: int
    payment_id: int
    transaction_number: str
    amount: object
    currency: str
    status: str
    checkout_request_id: str | None = None
    message: str
    phone_number: str


@router.post(
    "/exit/identify",
)
async def identify_qr_exit_session(
    data: QRAccessExitIdentifyRequest,
    qr_service: QRAccessTokenServiceDep,
    parking_session_service=Depends(get_parking_session_service),
):
    """
    Identify the latest parking session awaiting physical exit.

    This endpoint does not perform payment or physical checkout.
    It only validates the EXIT QR token, identifies the vehicle's
    current parking session at the QR facility, and reports whether
    payment is still required.
    """

    try:
        qr_access_token = await qr_service.resolve_public_token(
            raw_token=data.token,
            purpose=QRAccessPurpose.EXIT,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    normalized_registration = "".join(
        data.registration_number.split()
    ).upper()

    session_query = (
        select(ParkingSession)
        .join(ParkingBay, ParkingBay.id == ParkingSession.parking_bay_id)
        .join(ParkingZone, ParkingZone.id == ParkingBay.zone_id)
        .where(
            ParkingZone.facility_id == qr_access_token.facility_id,
            ParkingSession.vehicle_registration == normalized_registration,
            ParkingSession.exit_time.is_(None),
            ParkingSession.status.in_(
                (
                    SessionStatus.ACTIVE,
                    SessionStatus.COMPLETED,
                )
            ),
        )
        .order_by(
            ParkingSession.status.desc(),
            ParkingSession.entry_time.desc(),
        )
        .limit(1)
    )

    result = await parking_session_service.repository.db.execute(
        session_query
    )
    parking_session = result.scalar_one_or_none()

    if parking_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No active parking session or completed session awaiting "
                f"physical exit was found for {normalized_registration}."
            ),
        )

    payment_required = parking_session.status == SessionStatus.ACTIVE

    if payment_required:
        message = (
            f"Parking session {parking_session.session_number} was found for "
            f"{parking_session.vehicle_registration}. Payment is required "
            "before physical QR checkout can be completed."
        )
    else:
        message = (
            f"Parking session {parking_session.session_number} was found for "
            f"{parking_session.vehicle_registration}. Payment is already "
            "completed and the vehicle is ready for physical QR checkout."
        )

    return {
        "valid": True,
        "facility_id": qr_access_token.facility_id,
        "parking_session_id": parking_session.id,
        "session_number": parking_session.session_number,
        "registration_number": parking_session.vehicle_registration,
        "status": parking_session.status.value,
        "payment_status": (
            parking_session.payment_status.value
            if parking_session.payment_status is not None
            else None
        ),
        "payment_required": payment_required,
        "message": message,
    }


class QRAccessExitCheckoutRequest(BaseModel):
    """Physical checkout payload used by the public QR exit page."""

    token: str = Field(min_length=1)
    registration_number: str = Field(min_length=1)


@router.post(
    "/exit/checkout",
)
async def checkout_qr_exit_vehicle(
    data: QRAccessExitCheckoutRequest,
    qr_service: QRAccessTokenServiceDep,
    parking_session_service=Depends(get_parking_session_service),
):
    """
    Complete the physical exit of a vehicle whose parking payment
    has already been completed.

    This endpoint validates the public EXIT QR token and facility
    before delegating the actual physical checkout lifecycle to
    ParkingSessionService.
    """

    try:
        qr_access_token = await qr_service.resolve_public_token(
            raw_token=data.token,
            purpose=QRAccessPurpose.EXIT,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    normalized_registration = "".join(
        data.registration_number.split()
    ).upper()

    session_query = (
        select(ParkingSession)
        .join(
            ParkingBay,
            ParkingBay.id == ParkingSession.parking_bay_id,
        )
        .join(
            ParkingZone,
            ParkingZone.id == ParkingBay.zone_id,
        )
        .where(
            ParkingZone.facility_id == qr_access_token.facility_id,
            ParkingSession.vehicle_registration == normalized_registration,
            ParkingSession.exit_time.is_(None),
            ParkingSession.status == SessionStatus.COMPLETED,
        )
        .order_by(ParkingSession.entry_time.desc())
        .limit(1)
    )

    result = await parking_session_service.repository.db.execute(
        session_query
    )
    parking_session = result.scalar_one_or_none()

    if parking_session is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Parking payment is not yet completed for "
                f"{normalized_registration}, or the vehicle has already exited."
            ),
        )

    # ------------------------------------------------------
    # Physical checkout
    #
    # The session has already been COMPLETED by the payment
    # workflow. Do NOT send it through the normal active-session
    # checkout path again. Record the physical exit directly
    # here, then release the bay.
    #
    # This is intentionally limited to the QR EXIT endpoint.
    # All other checkout flows remain unchanged.
    # ------------------------------------------------------

    parking_session.exit_time = utc_now()
    parking_session.exit_method = ExitMethod.QR_CODE

    await parking_session_service.repository.save(
        parking_session,
    )

    parking_bay = (
        await parking_session_service.parking_bay_repository.release_bay(
            parking_session.parking_bay_id,
        )
    )

    if parking_bay is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parking bay not found.",
        )

    await parking_session_service.repository.db.commit()

    await parking_session_service.repository.db.refresh(
        parking_session,
    )

    # Preserve the existing notification behaviour without allowing
    # notification delivery to interfere with physical checkout.
    try:
        await parking_session_service._create_session_notification(
            parking_session=parking_session,
            notification_type=NotificationType.SESSION_CHECKED_OUT,
            title="Vehicle Exited",
            message=(
                f"Your vehicle "
                f"{parking_session.vehicle_registration} "
                f"has exited the parking facility. "
                f"Session: "
                f"{parking_session.session_number}."
            ),
        )
    except Exception:
        pass

    return {
        "valid": True,
        "parking_session_id": parking_session.id,
        "registration_number": parking_session.vehicle_registration,
        "status": parking_session.status.value,
        "exit_method": (
            parking_session.exit_method.value
            if parking_session.exit_method is not None
            else ExitMethod.QR_CODE.value
        ),
        "exit_time": parking_session.exit_time,
        "message": (
            f"Vehicle {parking_session.vehicle_registration} exited successfully. "
            "The parking bay has been released."
        ),
    }



def _normalize_qr_mpesa_phone(value: str) -> str:
    """Normalize a Kenyan M-Pesa number to 2547XXXXXXXX."""

    import re

    digits = re.sub(r"\D", "", value or "")

    if digits.startswith("00"):
        digits = digits[2:]

    if digits.startswith("0"):
        digits = "254" + digits[1:]
    elif digits.startswith("7") and len(digits) == 9:
        digits = "254" + digits

    if not re.fullmatch(r"2547\d{8}", digits):
        raise ValueError(
            "Please provide a valid Kenyan Safaricom number, "
            "for example 0712345678 or 254712345678."
        )

    return digits


@router.post(
    "/exit/payment/stk-push",
    response_model=QRAccessExitPaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def initiate_qr_exit_payment(
    data: QRAccessExitPaymentRequest,
    qr_service: QRAccessTokenServiceDep,
    payment_service: PaymentServiceDep,
    parking_session_service=Depends(get_parking_session_service),
) -> QRAccessExitPaymentResponse:
    """
    Initiate an M-Pesa STK Push for the parking session identified
    through a valid public EXIT QR token.

    The payable amount is calculated exclusively by PaymentService.
    The mobile page supplies only the payer's phone number.
    """

    try:
        qr_access_token = await qr_service.resolve_public_token(
            raw_token=data.token,
            purpose=QRAccessPurpose.EXIT,
        )

        normalized_registration = "".join(
            data.registration_number.split()
        ).upper()

        session_query = (
            select(ParkingSession)
            .join(
                ParkingBay,
                ParkingBay.id == ParkingSession.parking_bay_id,
            )
            .join(
                ParkingZone,
                ParkingZone.id == ParkingBay.zone_id,
            )
            .where(
                ParkingZone.facility_id == qr_access_token.facility_id,
                ParkingSession.vehicle_registration == normalized_registration,
                ParkingSession.exit_time.is_(None),
                ParkingSession.status == SessionStatus.ACTIVE,
            )
            .order_by(ParkingSession.entry_time.desc())
            .limit(1)
        )

        result = await parking_session_service.repository.db.execute(
            session_query
        )
        parking_session = result.scalar_one_or_none()

        if parking_session is None:
            raise ValueError(
                f"No ACTIVE parking session was found for {normalized_registration}."
            )

        payer_phone = _normalize_qr_mpesa_phone(
            data.mobile_number
        )

        payment_result = await payment_service.initiate_operator_mpesa_session_payment(
            parking_session_id=parking_session.id,
            payer_phone=payer_phone,
            notes="QR exit M-Pesa payment",
        )

        masked_phone = (
            f"{payer_phone[:6]}****{payer_phone[-2:]}"
        )

        return QRAccessExitPaymentResponse(
            valid=True,
            parking_session_id=payment_result["parking_session_id"],
            payment_id=payment_result["payment_id"],
            transaction_number=payment_result["transaction_number"],
            amount=payment_result["amount"],
            currency=payment_result["currency"],
            status=payment_result["status"],
            checkout_request_id=payment_result["checkout_request_id"],
            message=payment_result["message"],
            phone_number=masked_phone,
        )

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/resolve",
    response_model=QRAccessTokenResolveResponse,
)
async def resolve_qr_access_token(
    data: QRAccessTokenResolveRequest,
    current_user: CurrentFacilityAttendantDep,
    service: QRAccessTokenServiceDep,
) -> QRAccessTokenResolveResponse:
    """
    Resolve and validate a QR access token.

    This endpoint is currently authenticated and
    facility-scoped.

    The mobile QR entry-identification endpoint is
    public and uses the token itself to establish
    the facility context.
    """

    facility_id = _require_facility(current_user)

    try:
        qr_access_token = await service.resolve_token(
            raw_token=data.token,
            facility_id=facility_id,
            purpose=QRAccessPurpose.ENTRY,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return QRAccessTokenResolveResponse(
        valid=True,
        facility_id=qr_access_token.facility_id,
        purpose=qr_access_token.purpose,
        expires_at=qr_access_token.expires_at,
        message="QR access token is valid.",
    )


@router.post(
    "/entry/identify",
    response_model=QRAccessEntryIdentifyResponse,
)
async def identify_qr_entry_vehicle(
    data: QRAccessEntryIdentifyRequest,
    qr_service: QRAccessTokenServiceDep,
    vehicle_service: VehicleServiceDep,
) -> QRAccessEntryIdentifyResponse:
    """
    Identify a vehicle for QR-based parking entry.

    This is a public/mobile-facing endpoint.

    The QR token establishes the facility and must be:
    - valid
    - active
    - an ENTRY token
    - unexpired

    The supplied registration number is normalized by the
    existing VehicleService and VehicleRepository logic.

    This endpoint ONLY identifies the vehicle.

    It does NOT:
    - authenticate the driver
    - expose customer information
    - create a parking session
    - create a reservation
    """

    try:
        qr_access_token = await qr_service.resolve_public_token(
            raw_token=data.token,
            purpose=QRAccessPurpose.ENTRY,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    normalized_registration = "".join(
        data.registration_number.split()
    ).upper()

    try:
        vehicle = await vehicle_service.get_by_registration_number(
            registration_number=data.registration_number,
        )
    except ValueError:
        return QRAccessEntryIdentifyResponse(
            valid=True,
            facility_id=qr_access_token.facility_id,
            purpose=qr_access_token.purpose,
            expires_at=qr_access_token.expires_at,
            registration_number=normalized_registration,
            vehicle_id=None,
            registered=False,
            vehicle_active=False,
            message=(
                "Vehicle is not registered. "
                "Continue as a drive-in customer."
            ),
        )

    return QRAccessEntryIdentifyResponse(
        valid=True,
        facility_id=qr_access_token.facility_id,
        purpose=qr_access_token.purpose,
        expires_at=qr_access_token.expires_at,
        registration_number=vehicle.registration_number,
        vehicle_id=vehicle.id,
        registered=True,
        vehicle_active=vehicle.is_active,
        message=(
            "Registered vehicle identified. "
            "Driver authentication is required."
        ),
    )


@router.get(
    "/tokens",
    response_model=list[QRAccessTokenResponse],
)
async def get_qr_access_tokens(
    current_user: CurrentFacilityAttendantDep,
    service: QRAccessTokenServiceDep,
) -> list[QRAccessTokenResponse]:
    """
    Get all QR access tokens belonging to the
    authenticated user's facility.
    """

    facility_id = _require_facility(current_user)

    return await service.get_facility_tokens(
        facility_id=facility_id,
    )


@router.get(
    "/tokens/active",
    response_model=list[QRAccessTokenResponse],
)
async def get_active_qr_access_tokens(
    current_user: CurrentFacilityAttendantDep,
    service: QRAccessTokenServiceDep,
) -> list[QRAccessTokenResponse]:
    """
    Get active QR access tokens belonging to the
    authenticated user's facility.
    """

    facility_id = _require_facility(current_user)

    return await service.get_active_facility_tokens(
        facility_id=facility_id,
    )


@router.patch(
    "/tokens/{token_id}/deactivate",
    response_model=QRAccessTokenResponse,
)
async def deactivate_qr_access_token(
    token_id: int,
    current_user: CurrentFacilityAttendantDep,
    service: QRAccessTokenServiceDep,
) -> QRAccessTokenResponse:
    """
    Deactivate a QR access token.
    """

    facility_id = _require_facility(current_user)

    try:
        qr_access_token = await service.deactivate_token(
            token_id=token_id,
            facility_id=facility_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return qr_access_token


@router.patch(
    "/tokens/{token_id}/activate",
    response_model=QRAccessTokenResponse,
)
async def activate_qr_access_token(
    token_id: int,
    current_user: CurrentFacilityAttendantDep,
    service: QRAccessTokenServiceDep,
) -> QRAccessTokenResponse:
    """
    Reactivate a QR access token if it has not expired.
    """

    facility_id = _require_facility(current_user)

    try:
        qr_access_token = await service.activate_token(
            token_id=token_id,
            facility_id=facility_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return qr_access_token