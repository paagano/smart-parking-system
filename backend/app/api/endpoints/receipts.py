"""
Receipt API Endpoints.

REST API endpoints for SmartPark receipt management.

Responsibilities
----------------
- Retrieve a customer's receipts
- Retrieve a receipt by ID
- Retrieve a receipt by receipt number
- Publicly verify a receipt
- Generate a receipt PDF
- Regenerate a receipt PDF
- Download a receipt PDF
- Obtain a receipt PDF access URL

Business logic belongs in ReceiptService.
Persistence belongs in ReceiptRepository.
Storage operations belong in StorageService.
"""

from __future__ import annotations

from html import escape
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Response,
)
from fastapi.responses import HTMLResponse

from app.api.dependencies.auth import (
    get_current_active_user,
)

from app.api.dependencies.receipts import (
    ReceiptServiceDep,
)

from app.exceptions.handlers import (
    NotFoundException,
)

from app.models.user import User

from app.schemas.receipt import (
    ReceiptListResponse,
    ReceiptLookupResponse,
    ReceiptResponse,
    ReceiptVerificationResponse,
)


# ==========================================================
# Router
# ==========================================================

router = APIRouter(
    prefix="/receipts",
    tags=["Receipts"],
)


# ==========================================================
# Get My Receipts
# ==========================================================


@router.get(
    "",
    response_model=ReceiptListResponse,
    summary="Get My Receipts",
)
async def get_my_receipts(
    service: ReceiptServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    limit: int = Query(
        default=100,
        ge=1,
        le=100,
        description="Maximum number of receipts to return.",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of receipts to skip.",
    ),
) -> ReceiptListResponse:
    """
    Retrieve receipts belonging to the authenticated user.
    """

    return await service.get_customer_receipts(
        customer_id=current_user.id,
        limit=limit,
        offset=offset,
    )


# ==========================================================
# Public Receipt Lookup
# ==========================================================


@router.get(
    "/lookup/{receipt_number}",
    response_model=ReceiptLookupResponse,
    summary="Public Receipt Lookup",
)
async def lookup_receipt(
    receipt_number: str,
    service: ReceiptServiceDep,
) -> ReceiptLookupResponse:
    """
    Retrieve public-facing receipt information.

    Sensitive information such as the verification token
    and internal storage details are excluded by
    ReceiptService.
    """

    return await service.lookup_receipt(
        receipt_number=receipt_number,
    )


# ==========================================================
# Public HTML Receipt Verification
# ==========================================================


@router.get(
    "/public/verify/{receipt_number}",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def verify_receipt_public_page(
    receipt_number: str,
    service: ReceiptServiceDep,
    verification_token: str = Query(
        ...,
        min_length=1,
        description="Receipt verification token.",
    ),
) -> HTMLResponse:
    """
    Customer-facing receipt verification page.

    This uses the existing ReceiptService verification logic.
    Only the presentation is changed from JSON to HTML.
    """

    try:
        verification = await service.verify_receipt(
            receipt_number=receipt_number,
            verification_token=verification_token,
        )

    except ValueError:
        return HTMLResponse(
            content=_verification_html(
                valid=False,
                receipt_number=receipt_number,
            ),
            status_code=404,
        )

    valid = bool(
        getattr(
            verification,
            "valid",
            False,
        )
    )

    return HTMLResponse(
        content=_verification_html(
            valid=valid,
            receipt_number=getattr(
                verification,
                "receipt_number",
                receipt_number,
            ),
            status=getattr(
                verification,
                "status",
                None,
            ),
            receipt_type=getattr(
                verification,
                "receipt_type",
                None,
            ),
            total_amount=getattr(
                verification,
                "total_amount",
                None,
            ),
            currency=getattr(
                verification,
                "currency",
                None,
            ),
            payment_transaction_id=getattr(
                verification,
                "payment_transaction_id",
                None,
            ),
            paid_at=getattr(
                verification,
                "paid_at",
                None,
            ),
            verified_at=getattr(
                verification,
                "verified_at",
                None,
            ),
        ),
        status_code=200 if valid else 404,
    )


# ==========================================================
# Verify Receipt - JSON API
# ==========================================================


@router.get(
    "/verify/{receipt_number}",
    response_model=ReceiptVerificationResponse,
    summary="Verify Receipt",
)
async def verify_receipt(
    receipt_number: str,
    service: ReceiptServiceDep,
    verification_token: str = Query(
        ...,
        min_length=1,
        description="Receipt verification token.",
    ),
) -> ReceiptVerificationResponse:
    """
    Verify a receipt using its receipt number and
    verification token.

    This endpoint does not require authentication.
    """

    return await service.verify_receipt(
        receipt_number=receipt_number,
        verification_token=verification_token,
    )


# ==========================================================
# Get Receipt by ID
# ==========================================================


@router.get(
    "/{receipt_id}",
    response_model=ReceiptResponse,
    summary="Get Receipt",
)
async def get_receipt(
    receipt_id: int,
    service: ReceiptServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> ReceiptResponse:
    """
    Retrieve a receipt by ID.

    The receipt must belong to the authenticated user.
    """

    receipt = await service.get_receipt(
        receipt_id,
    )

    if receipt.customer_id != current_user.id:
        raise NotFoundException(
            "Receipt not found."
        )

    return receipt


# ==========================================================
# Get Receipt by Receipt Number
# ==========================================================


@router.get(
    "/number/{receipt_number}",
    response_model=ReceiptResponse,
    summary="Get Receipt by Receipt Number",
)
async def get_receipt_by_number(
    receipt_number: str,
    service: ReceiptServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> ReceiptResponse:
    """
    Retrieve a receipt using its public receipt number.

    The receipt must belong to the authenticated user.
    """

    receipt = await service.get_by_receipt_number(
        receipt_number,
    )

    if receipt.customer_id != current_user.id:
        raise NotFoundException(
            "Receipt not found."
        )

    return receipt


# ==========================================================
# Generate Receipt PDF
# ==========================================================


@router.post(
    "/{receipt_id}/generate",
    response_model=ReceiptResponse,
    summary="Generate Receipt PDF",
)
async def generate_receipt_pdf(
    receipt_id: int,
    service: ReceiptServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> ReceiptResponse:
    """
    Generate and store the PDF representation of a receipt.
    """

    receipt = await service.get_receipt(
        receipt_id,
    )

    if receipt.customer_id != current_user.id:
        raise NotFoundException(
            "Receipt not found."
        )

    return await service.generate_receipt(
        receipt_id=receipt_id,
    )


# ==========================================================
# Regenerate Receipt PDF
# ==========================================================


@router.post(
    "/{receipt_id}/regenerate",
    response_model=ReceiptResponse,
    summary="Regenerate Receipt PDF",
)
async def regenerate_receipt_pdf(
    receipt_id: int,
    service: ReceiptServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> ReceiptResponse:
    """
    Regenerate the stored PDF representation of a receipt.
    """

    receipt = await service.get_receipt(
        receipt_id,
    )

    if receipt.customer_id != current_user.id:
        raise NotFoundException(
            "Receipt not found."
        )

    return await service.regenerate_receipt(
        receipt_id=receipt_id,
    )


# ==========================================================
# Receipt PDF URL
# ==========================================================


@router.get(
    "/{receipt_id}/url",
    summary="Get Receipt PDF URL",
)
async def get_receipt_url(
    receipt_id: int,
    service: ReceiptServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    expires_in: int = Query(
        default=3600,
        ge=60,
        le=86400,
        description=(
            "Number of seconds for which the access URL "
            "should remain valid."
        ),
    ),
) -> dict[str, str]:
    """
    Generate an access URL for the receipt PDF.
    """

    receipt = await service.get_receipt(
        receipt_id,
    )

    if receipt.customer_id != current_user.id:
        raise NotFoundException(
            "Receipt not found."
        )

    url = await service.get_receipt_url(
        receipt_id=receipt_id,
        expires_in=expires_in,
    )

    return {
        "receipt_number": receipt.receipt_number,
        "url": url,
    }


# ==========================================================
# Download Receipt PDF
# ==========================================================


@router.get(
    "/{receipt_id}/download",
    summary="Download Receipt PDF",
)
async def download_receipt_pdf(
    receipt_id: int,
    service: ReceiptServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> Response:
    """
    Download the generated receipt PDF.
    """

    receipt = await service.get_receipt(
        receipt_id,
    )

    if receipt.customer_id != current_user.id:
        raise NotFoundException(
            "Receipt not found."
        )

    pdf_bytes = await service.download_receipt_pdf(
        receipt_id=receipt_id,
    )

    filename = f"{receipt.receipt_number}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            ),
        },
    )


# ==========================================================
# Customer-Facing HTML Helpers
# ==========================================================


def _display_value(
    value: object | None,
) -> str:
    """
    Convert a verification value into safe display text.
    """

    if value is None:
        return "—"

    raw = getattr(
        value,
        "value",
        value,
    )

    text = str(raw).strip()

    if not text:
        return "—"

    return escape(text)


def _verification_html(
    *,
    valid: bool,
    receipt_number: object | None,
    status: object | None = None,
    receipt_type: object | None = None,
    total_amount: object | None = None,
    currency: object | None = None,
    payment_transaction_id: object | None = None,
    paid_at: object | None = None,
    verified_at: object | None = None,
) -> str:
    """
    Build the customer-facing receipt verification page.
    """

    receipt = _display_value(
        receipt_number,
    )

    status_text = _display_value(
        status,
    )

    receipt_type_text = _display_value(
        receipt_type,
    )

    amount = _display_value(
        total_amount,
    )

    currency_text = _display_value(
        currency,
    )

    transaction = _display_value(
        payment_transaction_id,
    )

    paid = _display_value(
        paid_at,
    )

    verified = _display_value(
        verified_at,
    )

    if valid:

        result_title = "Receipt Verified"

        result_message = (
            "This receipt has been successfully verified "
            "against the SmartPark payment records."
        )

        badge = "VALID RECEIPT"

        icon = "✓"

        accent = "#00a878"
        accent_soft = "#eafaf4"
        accent_border = "#b7ead8"
        accent_text = "#075f49"

        details = f"""
        <div class="details">

          <div class="row">
            <span>Receipt Number</span>
            <strong>{receipt}</strong>
          </div>

          <div class="row">
            <span>Status</span>
            <strong>{status_text}</strong>
          </div>

          <div class="row">
            <span>Receipt Type</span>
            <strong>{receipt_type_text}</strong>
          </div>

          <div class="row">
            <span>Amount</span>
            <strong>{amount} {currency_text}</strong>
          </div>

          <div class="row">
            <span>Payment Transaction</span>
            <strong>{transaction}</strong>
          </div>

          <div class="row">
            <span>Paid At</span>
            <strong>{paid}</strong>
          </div>

          <div class="row">
            <span>Verified At</span>
            <strong>{verified}</strong>
          </div>

        </div>
        """

        note = (
            "✓ The receipt details below are confirmed "
            "by SmartPark AI."
        )

    else:

        result_title = (
            "Receipt Could Not Be Verified"
        )

        result_message = (
            "The receipt number or verification code "
            "could not be validated. Please confirm "
            "the receipt details and try again."
        )

        badge = "VERIFICATION FAILED"

        icon = "!"

        accent = "#c6284a"
        accent_soft = "#fff0f3"
        accent_border = "#ffc4d0"
        accent_text = "#8d1733"

        details = f"""
        <div class="details">

          <div class="row">
            <span>Receipt Number</span>
            <strong>{receipt}</strong>
          </div>

        </div>
        """

        note = (
            "⚠ Please do not rely on this receipt until "
            "it has been successfully verified."
        )

    return f"""<!doctype html>

<html lang="en">

<head>

  <meta charset="utf-8">

  <meta
    name="viewport"
    content="width=device-width, initial-scale=1"
  >

  <meta
    name="robots"
    content="noindex,nofollow"
  >

  <title>
    {result_title} — SmartPark AI
  </title>

  <style>

    :root {{
      --navy: #071b2e;
      --slate: #53657a;
      --border: #dfe7ef;
      --bg: #f5f8fb;
      --white: #ffffff;
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{

      margin: 0;

      min-height: 100vh;

      background: var(--bg);

      color: var(--navy);

      font-family:
        Inter,
        ui-sans-serif,
        system-ui,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

      display: flex;

      align-items: center;

      justify-content: center;

      padding: 24px;

    }}

    .shell {{
      width: 100%;
      max-width: 720px;
    }}

    .brand {{
      text-align: center;
      margin-bottom: 18px;
    }}

    .brand-name {{
      font-size: 26px;
      font-weight: 900;
      letter-spacing: -0.5px;
    }}

    .brand-sub {{
      margin-top: 4px;
      color: var(--slate);
      font-size: 13px;
    }}

    .card {{

      background: var(--white);

      border: 1px solid var(--border);

      border-radius: 24px;

      box-shadow:
        0 16px 45px
        rgba(7, 27, 46, 0.10);

      overflow: hidden;

    }}

    .hero {{

      padding: 30px;

      background: var(--navy);

      color: white;

      text-align: center;

    }}

    .icon {{

      width: 62px;

      height: 62px;

      margin: 0 auto 14px;

      border-radius: 50%;

      display: grid;

      place-items: center;

      font-size: 30px;

      font-weight: 900;

      background: {accent};

    }}

    .badge {{

      display: inline-block;

      padding: 6px 12px;

      border-radius: 999px;

      font-size: 11px;

      font-weight: 900;

      letter-spacing: 1px;

      background: {accent_soft};

      color: {accent_text};

    }}

    h1 {{

      margin: 12px 0 7px;

      font-size: 28px;

      letter-spacing: -0.7px;

    }}

    .message {{

      margin: 0 auto;

      max-width: 560px;

      color: #d9e6f2;

      font-size: 14px;

      line-height: 1.7;

    }}

    .body {{

      padding: 28px 30px 30px;

    }}

    .verified-note {{

      border: 1px solid {accent_border};

      background: {accent_soft};

      color: {accent_text};

      border-radius: 14px;

      padding: 13px 15px;

      margin-bottom: 20px;

      font-size: 13px;

      font-weight: 700;

    }}

    .details {{

      border: 1px solid var(--border);

      border-radius: 16px;

      overflow: hidden;

    }}

    .row {{

      display: flex;

      justify-content: space-between;

      gap: 20px;

      padding: 14px 16px;

      border-bottom: 1px solid var(--border);

      font-size: 13px;

    }}

    .row:last-child {{
      border-bottom: 0;
    }}

    .row span {{
      color: var(--slate);
    }}

    .row strong {{

      text-align: right;

      overflow-wrap: anywhere;

    }}

    .footer {{

      text-align: center;

      color: var(--slate);

      font-size: 11px;

      line-height: 1.6;

      margin-top: 18px;

    }}

    @media (max-width: 560px) {{

      body {{
        padding: 12px;
      }}

      .hero,
      .body {{
        padding-left: 20px;
        padding-right: 20px;
      }}

      h1 {{
        font-size: 24px;
      }}

      .row {{

        flex-direction: column;

        gap: 5px;

      }}

      .row strong {{
        text-align: left;
      }}

    }}

  </style>

</head>

<body>

  <main class="shell">

    <div class="brand">

      <div class="brand-name">
        SmartPark AI
      </div>

      <div class="brand-sub">
        Smart Parking Management System
      </div>

    </div>


    <section class="card">

      <div class="hero">

        <div class="icon">
          {icon}
        </div>

        <div class="badge">
          {badge}
        </div>

        <h1>
          {result_title}
        </h1>

        <p class="message">
          {escape(result_message)}
        </p>

      </div>


      <div class="body">

        <div class="verified-note">
          {note}
        </div>

        {details}

      </div>

    </section>


    <div class="footer">

      SmartPark AI · This is a
      computer-generated receipt
      verification page.

      <br>

      For assistance, please contact
      the parking facility or SmartPark
      support.

    </div>

  </main>

</body>

</html>"""