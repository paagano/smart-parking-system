"""
Business service for Payment Transactions.

The Payment Service coordinates all financial operations
within the Smart Parking System.

Responsibilities
----------------
- Validate payments
- Prevent duplicate transactions
- Generate transaction numbers
- Persist transactions
- Retrieve transactions

Future Responsibilities
-----------------------
- Wallet integration
- Loyalty Engine
- Receipt generation
- Notifications
- Accounting exports
- Provider integrations
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    NotificationChannel,
    NotificationPriority,
    NotificationType,
    PaymentMethod,
    PaymentPurpose,
    PaymentStatus,
    PaymentProvider,
    ReservationPaymentStatus,
    ReservationStatus,
    SessionPaymentStatus,
    SessionStatus,
    WalletTransactionType,
)
from app.models.payment_transaction import PaymentTransaction
from app.models.enums import LoyaltyPointTransactionType
from app.models.wallet import Wallet
from app.repositories.payment_repository import PaymentRepository
from app.repositories.parking_reservation_repository import (
    ParkingReservationRepository,
)
from app.repositories.parking_session_repository import (
    ParkingSessionRepository,
)
from app.repositories.loyalty_repository import LoyaltyRepository
from app.schemas.mpesa_callback import MpesaCallbackRequest
from app.schemas.notification import NotificationCreate
from app.schemas.payment import (
    PaymentCreate,
    RefundCreate,
    ReversalCreate,
    ReservationPaymentCreate,
    SessionPaymentCreate,
    WalletTopUpCreate,
)
from app.schemas.payment_provider import PaymentProviderResponse
from app.services.notification_service import NotificationService
from app.services.receipt_service import ReceiptService
from app.services.payment_providers.factory import PaymentProviderFactory
from app.services.wallet_service import WalletService
from app.services.loyalty_service import LoyaltyService
from app.services.pricing_service import PricingService


# ==========================================================
# Loyalty Configuration
# ==========================================================

# 1 loyalty point for every KES 100 successfully paid.
#
# This configuration of the commercial loyalty rule can be
# changed later without changing the payment workflow.
# Example:
#     Decimal("0.01") -> 1 point per KES 100
#     Decimal("0.02") -> 1 point per KES 50
#

LOYALTY_POINTS_PER_KES = Decimal("0.01")

# Confirmed commercial redemption rule:
# 1 loyalty point = KES 1.00.
LOYALTY_POINT_VALUE_KES = Decimal("1.00")

class PaymentService:
    """
    Business logic for payment transactions.
    """

    def __init__(
        self,
        *,
        db: AsyncSession,
        repository: PaymentRepository,
        reservation_repository: ParkingReservationRepository,
        session_repository: ParkingSessionRepository,
        pricing_service: PricingService,
        wallet_service: WalletService,
        notification_service: NotificationService,
        receipt_service: ReceiptService,
    ) -> None:
        self.db = db
        self.repository = repository
        self.reservation_repository = reservation_repository
        self.session_repository = session_repository
        self.pricing_service = pricing_service
        #
        # Wallet integration.
        #
        # Wallet operations are delegated to WalletService.
        #
        self.wallet_service = wallet_service

        #
        # Notification integration.
        #
        # Notification failures are isolated from the core
        # payment transaction so a successful payment is never
        # converted into a failed operation because notification
        # creation fails.
        #
        self.notification_service = notification_service
        self.receipt_service = receipt_service

        # ==========================================================
        # Loyalty integration.
        # ==========================================================

        # Loyalty persistence is kept behind LoyaltyRepository and
        # business rules are delegated to LoyaltyService.
        #
        # The existing NotificationService is passed through so that
        # LoyaltyService can generate notifications for loyalty events
        # such as points earned and tier upgrades.
        self.loyalty_service = LoyaltyService(
            db=db,
            repository=LoyaltyRepository(db),
            notification_service=notification_service,
        )

    # ==========================================================
    # Internal Helpers
    # ==========================================================

    def _generate_transaction_number(self) -> str:
        """
        Generate a unique transaction number.

        Example
        -------
        PAY-20260802-143255-A3F9C2
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        suffix = uuid.uuid4().hex[:6].upper()
        return f"PAY-{timestamp}-{suffix}"

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        """
        Normalize a monetary value to two decimal places.
        """
        return value.quantize(Decimal("0.01"))

    async def _create_payment_notification(
        self,
        *,
        payment: PaymentTransaction,
        notification_type: NotificationType,
        title: str,
        message: str,
    ) -> None:
        """
        Create an in-app notification for a payment event.

        Payment notifications are deliberately isolated from the
        payment transaction. A notification failure must never cause
        an already successful payment operation to fail or roll back.

        Notifications are currently persisted as IN_APP messages with
        PENDING delivery status. Email, SMS and push delivery will be
        handled by the notification channel-delivery layer later.
        """

        if payment.customer_id is None:
            return 0

        try:
            await self.notification_service.create_notification(
                data=NotificationCreate(
                    user_id=payment.customer_id,
                    type=notification_type,
                    channel=NotificationChannel.IN_APP,
                    priority=NotificationPriority.NORMAL,
                    title=title,
                    message=message.replace(
                        "Your payment ",
                        f"Your {payment.payment_purpose.value} payment ",
                        1,
                    ),
                    related_entity_type="PAYMENT_TRANSACTION",
                    related_entity_id=payment.id,
                ),
            )
        except Exception:
            # Notification failures must not break payment processing.
            pass

    async def _validate_loyalty_points_contribution(
        self,
        *,
        customer_id: int | None,
        points: int,
        expected_amount: Decimal,
        remaining_amount: Decimal,
    ) -> None:
        """
        Validate an optional loyalty-points contribution.

        One loyalty point is worth KES 1.00. The amount supplied
        to the external payment provider represents only the
        remaining monetary amount after the loyalty contribution.

        Existing payment behaviour is unchanged when ``points``
        is zero.
        """

        if points < 0:
            raise ValueError(
                "Loyalty points to redeem cannot be negative."
            )

        expected_amount = self._money(expected_amount)
        remaining_amount = self._money(remaining_amount)

        if points == 0:
            if expected_amount != remaining_amount:
                raise ValueError(
                    "Payment amount does not match the required amount."
                )
            return

        if customer_id is None:
            raise ValueError(
                "Customer ID is required when redeeming loyalty points."
            )

        loyalty_value = (
            Decimal(points) * LOYALTY_POINT_VALUE_KES
        ).quantize(Decimal("0.01"))

        if loyalty_value > expected_amount:
            raise ValueError(
                "Loyalty points cannot exceed the payment amount."
            )

        expected_remaining = (
            expected_amount - loyalty_value
        ).quantize(Decimal("0.01"))

        if expected_remaining != remaining_amount:
            raise ValueError(
                "Payment amount must equal the required amount minus "
                "the loyalty-points contribution."
            )

        account = await self.loyalty_service.get_account(
            customer_id,
        )

        if not account.is_active:
            raise ValueError(
                "Loyalty account is inactive."
            )

        if account.points_balance < points:
            raise ValueError(
                "Insufficient loyalty points."
            )

    async def _redeem_loyalty_points_for_payment(
        self,
        *,
        payment: PaymentTransaction,
    ) -> None:
        """
        Redeem the loyalty points recorded on a successful payment.

        The payment transaction ID is used as the loyalty ledger
        reference, providing idempotency through LoyaltyService.
        """

        points = payment.loyalty_points_redeemed

        if points <= 0:
            return

        if payment.customer_id is None:
            raise ValueError(
                "Customer ID is required to redeem loyalty points."
            )

        await self.loyalty_service.redeem_points(
            customer_id=payment.customer_id,
            points=points,
            reference_type="PAYMENT_TRANSACTION",
            reference_id=payment.id,
            description=(
                f"Redeemed {points} loyalty points towards payment "
                f"{payment.transaction_number}."
            ),
        )

    async def _get_customer_wallet(self, customer_id: int) -> Wallet:
        """
        Retrieve the customer's wallet.

        Wallet lookup is delegated to WalletService.
        """
        return await self.wallet_service.get_wallet_by_customer(customer_id)

    async def _generate_payment_receipt(
        self,
        *,
        payment: PaymentTransaction,
    ) -> None:
        """
        Create and generate the receipt for a successful payment.

        Receipt failures are isolated from the already successful
        payment transaction.
        """

        try:
            receipt = await self.receipt_service.create_receipt(
                payment=payment,
            )

            await self.receipt_service.generate_receipt(
                receipt_id=receipt.id,
            )

        except Exception:
            #
            # Payment has already succeeded. A receipt-generation
            # failure must not turn the successful payment into
            # a failed API operation.
            #
            pass

    async def _award_loyalty_points(
        self,
        *,
        payment: PaymentTransaction,
    ) -> int:
        """
        Award loyalty points for an eligible successful parking payment.

        Rules
        -----
        - Only SUCCESSFUL payments earn points.
        - PARKING_SESSION and RESERVATION payments are eligible.
        - WALLET_TOPUP payments do not earn parking loyalty points.
        - The same payment cannot earn points twice because the payment
          transaction ID is used as the loyalty ledger reference and
          LoyaltyService provides idempotency.
        - Refund/reversal handling will be added later by reversing the
          corresponding loyalty ledger entry.

        Loyalty failures are isolated from the already successful payment
        so the payment itself is never converted into a failed operation.
        """

        if payment.status != PaymentStatus.SUCCESSFUL:
            return 0

        if payment.customer_id is None:
            return 0

        if payment.payment_purpose not in (
            PaymentPurpose.PARKING_SESSION,
            PaymentPurpose.RESERVATION,
        ):
            return 0

        try:
            #
            # Calculate points using the configurable commercial rate.
            # Decimal arithmetic avoids floating-point rounding issues.
            #
            points = int(
                (
                    payment.total_amount
                    * LOYALTY_POINTS_PER_KES
                ).to_integral_value(
                    rounding=ROUND_FLOOR,
                )
            )

            # Payments below the configured earning threshold earn zero.
            if points <= 0:
                return 0

            #
            # Every customer who makes an eligible successful parking
            # payment must have a loyalty account. Create it lazily when
            # the first eligible payment is completed.
            #
            await self.loyalty_service.get_or_create_account(
                customer_id=payment.customer_id,
            )

            await self.loyalty_service.award_points(
                customer_id=payment.customer_id,
                points=points,
                transaction_type=(
                    LoyaltyPointTransactionType.EARN
                ),
                reference_type="PAYMENT_TRANSACTION",
                reference_id=payment.id,
                description=(
                    f"Earned {points} loyalty points for "
                    f"{payment.payment_purpose.value} payment "
                    f"{payment.transaction_number}."
                ),
            )

            return points

        except Exception:
            #
            # The payment has already succeeded. Loyalty processing must
            # never make the successful financial transaction fail.
            #
            return 0

    # ==========================================================
    # Internal Payment Creator
    # ==========================================================

    async def _create_payment(
        self,
        payment: PaymentCreate,
        *,
        status: PaymentStatus = PaymentStatus.SUCCESSFUL,
        provider_response: PaymentProviderResponse | None = None,
    ) -> PaymentTransaction:
        """
        Internal helper used by all payment workflows.

        Creates and persists a PaymentTransaction.

        Notes
        -----
        - Does NOT commit the transaction.
        - The caller owns the transaction boundary.
        - The returned entity is fully synchronized with
          PostgreSQL and has a generated primary key.
        """
        #
        # Validate amounts are not negative.
        #
        if payment.subtotal_amount < 0:
            raise ValueError("Subtotal amount cannot be negative.")

        if payment.tax_amount < 0:
            raise ValueError("Tax amount cannot be negative.")

        if payment.total_amount < 0:
            raise ValueError("Total amount cannot be negative.")

        payment_transaction = PaymentTransaction(
            # ==================================================
            # Relationships
            # ==================================================
            reservation_id=getattr(payment, "reservation_id", None),
            parking_session_id=getattr(payment, "parking_session_id", None),
            customer_id=getattr(payment, "customer_id", None),
            parent_transaction_id=getattr(payment, "parent_transaction_id", None),
            # ==================================================
            # Identity
            # ==================================================
            transaction_number=self._generate_transaction_number(),
            # ==================================================
            # Payment Details
            # ==================================================
            payment_type=payment.payment_type,
            payment_purpose=payment.payment_purpose,
            payment_method=payment.payment_method,
            payment_provider=payment.payment_provider,
            currency=payment.currency,
            subtotal_amount=payment.subtotal_amount,
            discount_amount=payment.discount_amount,
            tax_amount=payment.tax_amount,
            total_amount=payment.total_amount,
            # ==================================================
            # Payer
            # ==================================================
            payer_name=payment.payer_name,
            payer_phone=payment.payer_phone,
            payer_email=payment.payer_email,
            #
            # Provider Information
            #
            provider_transaction_id=(
                provider_response.provider_reference
                if provider_response is not None
                else None
            ),
            provider_status_message=(
                provider_response.message
                if provider_response is not None
                else None
            ),
            provider_response=(
                provider_response.raw_response
                if provider_response is not None
                else None
            ),
            #
            # Audit
            #
            notes=payment.notes,
            status=(
                provider_response.status
                if provider_response is not None
                else status
            ),
            paid_at=(
                datetime.now(timezone.utc)
                if (
                    provider_response.status
                    if provider_response is not None
                    else status
                ) == PaymentStatus.SUCCESSFUL
                else None
            ),
        )

        await self.repository.save(payment_transaction)
        await self.repository.refresh(payment_transaction)

        if payment_transaction.id is None:
            raise RuntimeError(
                "Failed to generate PaymentTransaction primary key."
            )

        return payment_transaction

    # ==========================================================
    # Wallet Top-up
    # ==========================================================

    async def process_wallet_topup(
        self,
        payment: WalletTopUpCreate,
    ) -> PaymentTransaction:
        """
        Process a wallet top-up.

        Workflow
        --------
        Validate Request
              ↓
        Retrieve Customer Wallet
              ↓
        Create PaymentTransaction
              ↓
        Credit Wallet
              ↓
        Commit Transaction
        """
        if payment.customer_id is None:
            raise ValueError("Customer ID is required.")

        #
        # Retrieve customer's wallet.
        #
        wallet = await self._get_customer_wallet(payment.customer_id)

        try:
            #
            # Create payment transaction.
            #
            payment_transaction = await self._create_payment(payment)

            #
            # INTERNAL payments complete immediately.
            #
            if payment.payment_provider == PaymentProvider.INTERNAL:
                await self.wallet_service.credit_wallet(
                    wallet_id=wallet.id,
                    amount=payment.total_amount,
                    payment_transaction_id=payment_transaction.id,
                    created_by=payment.customer_id,
                    description="Wallet Top-up",
                    reference=payment_transaction.transaction_number,
                )

            #
            # MPESA / CARD / BANK transfers are asynchronous.
            #
            else:
                provider = PaymentProviderFactory.get_provider(
                    payment.payment_provider,
                )

                provider_response = await provider.process_payment(
                    payment=payment,
                )

                if not provider_response.success:
                    raise ValueError(
                        provider_response.message
                        or "Payment provider rejected the payment."
                    )

                payment_transaction.status = provider_response.status
                payment_transaction.provider_transaction_id = (
                    provider_response.provider_reference
                )
                payment_transaction.provider_status_message = (
                    provider_response.message
                )
                payment_transaction.provider_response = (
                    provider_response.raw_response
                )

                await self.repository.save(payment_transaction)

            #
            # Commit payment transaction.
            #
            await self.repository.commit()

            #
            # Refresh payment.
            #
            await self.repository.refresh(payment_transaction)

            #
            # Receipt.
            #
            if payment_transaction.status == PaymentStatus.SUCCESSFUL:
                await self._generate_payment_receipt(
                    payment=payment_transaction,
                )
            #
            # Notification.
            #
            if payment_transaction.status == PaymentStatus.PENDING:
                await self._create_payment_notification(
                    payment=payment_transaction,
                    notification_type=NotificationType.PAYMENT_INITIATED,
                    title="Payment Initiated",
                    message=(
                        f"Your payment "
                        f"{payment_transaction.transaction_number} "
                        f"has been initiated and is awaiting confirmation."
                    ),
                )
            elif payment_transaction.status == PaymentStatus.SUCCESSFUL:
                await self._create_payment_notification(
                    payment=payment_transaction,
                    notification_type=NotificationType.PAYMENT_SUCCESSFUL,
                    title="Payment Successful",
                    message=(
                        f"Your payment "
                        f"{payment_transaction.transaction_number} "
                        f"of KES {payment_transaction.total_amount} "
                        f"was successful."
                    ),
                )

            return payment_transaction

        except Exception:
            await self.repository.rollback()
            raise

    # ==========================================================
    # Parking Session Payment
    # ==========================================================

    async def process_session_payment(
        self,
        payment: SessionPaymentCreate,
    ) -> PaymentTransaction:
        """
        Process payment for a completed parking session.

        Workflow
        --------
        Parking Session
                ↓
        Validate
                ↓
        Validate Amount
                ↓
        Create Payment
                ↓
        Debit Wallet (if wallet payment)
                ↓
        Mark Session Paid
                ↓
        Commit Transaction
        """
        if payment.parking_session_id is None:
            raise ValueError("Parking session ID is required.")

        #
        # Retrieve parking session.
        #
        parking_session = await self.session_repository.get_by_id(
            payment.parking_session_id,
        )

        if parking_session is None:
            raise ValueError("Parking session not found.")

        #
        # Prevent duplicate payments.
        #
        if parking_session.is_paid:
            raise ValueError("Parking session has already been paid.")

        #
        # Active parking sessions may be paid out before physical exit.
        # Successful payment will transition the session to COMPLETED;
        # the IoT exit scanner remains responsible for confirming the
        # vehicle has physically left the premises.

        #
        # Recalculate the parking charge at the moment payment is requested.
        # For an active session, use the current time so the payable amount
        # reflects the latest elapsed parking duration. For a completed
        # session, retain the recorded exit time as the pricing endpoint
        # should use the actual completed parking duration.
        #
        pricing_exit_time = (
            parking_session.exit_time
            if parking_session.exit_time is not None
            else datetime.now(timezone.utc)
        )

        pricing_result = await self.pricing_service.calculate_for_session(
            vehicle_type=parking_session.vehicle_type,
            billing_type=parking_session.billing_type,
            entry_time=parking_session.entry_time,
            exit_time=pricing_exit_time,
        )

        expected_amount = pricing_result.total_amount.quantize(
            Decimal("0.01"),
        )
        received_amount = payment.total_amount.quantize(Decimal("0.01"))

        await self._validate_loyalty_points_contribution(
            customer_id=payment.customer_id,
            points=payment.loyalty_points_to_redeem,
            expected_amount=expected_amount,
            remaining_amount=received_amount,
        )

        try:
            #
            # Stamp the authoritative pricing calculation used for this
            # payment request onto the parking session.
            #
            # This is intentionally done after amount validation and inside
            # the existing transaction boundary. It ensures that the
            # calculated amount and duration used to determine the payable
            # amount are persisted without changing the existing payment
            # workflow.
            #
            parking_session.calculated_amount = expected_amount
            parking_session.duration_minutes = pricing_result.duration_minutes

            await self.session_repository.save(parking_session)

            #
            # Create payment transaction.
            #
            payment_transaction = await self._create_payment(payment)

            payment_transaction.loyalty_points_redeemed = (
                payment.loyalty_points_to_redeem
            )
            await self.repository.save(payment_transaction)

            #
            # Wallet payment.
            #
            if payment.payment_method == PaymentMethod.WALLET:
                wallet = await self._get_customer_wallet(payment.customer_id)

                await self.wallet_service.debit_wallet(
                    wallet_id=wallet.id,
                    amount=payment.total_amount,
                    payment_transaction_id=payment_transaction.id,
                    created_by=payment.customer_id,
                    reference=payment_transaction.transaction_number,
                    description="Parking session payment",
                )

            #
            # ======================================================
            # Resolve Payment Provider
            # ======================================================
            #
            # A full loyalty-points payment has no external monetary
            # amount to send to a provider. Partial redemption still
            # follows the existing provider flow using only the
            # remaining monetary amount.
            #
            if payment.total_amount > Decimal("0.00"):
                provider = PaymentProviderFactory.get_provider(
                    payment.payment_provider,
                )

                provider_response = await provider.process_payment(
                    payment=payment_transaction,
                )

                if not provider_response.success:
                    raise ValueError(
                        provider_response.message
                        or "Payment provider rejected the payment."
                    )

                #
                # Persist provider response.
                #
                payment_transaction.provider_transaction_id = (
                    provider_response.provider_reference
                )
                payment_transaction.provider_status_message = (
                    provider_response.message
                )
                payment_transaction.provider_response = (
                    provider_response.raw_response
                )
                payment_transaction.status = provider_response.status

                await self.repository.save(payment_transaction)

            else:
                # Full payment is covered by loyalty points.
                payment_transaction.status = PaymentStatus.SUCCESSFUL
                payment_transaction.paid_at = datetime.now(timezone.utc)
                await self.repository.save(payment_transaction)

            #
            # INTERNAL payments complete immediately.
            #
            if (
                payment.payment_provider == PaymentProvider.INTERNAL
                or payment.total_amount == Decimal("0.00")
            ):
                await self._complete_session_payment(
                    payment=payment_transaction,
                    paid_at=payment_transaction.paid_at,
                )

            #
            # Commit everything.
            #
            await self.repository.commit()

            #
            # Refresh entities.
            #
            await self.repository.refresh(payment_transaction)
            await self.session_repository.refresh(parking_session)

            #
            # Loyalty points redemption.
            #
            if (
                payment_transaction.status == PaymentStatus.SUCCESSFUL
                and payment_transaction.loyalty_points_redeemed > 0
            ):
                await self._redeem_loyalty_points_for_payment(
                    payment=payment_transaction,
                )

            #
            # Loyalty points earned.
            #
            if payment_transaction.status == PaymentStatus.SUCCESSFUL:
                loyalty_points = await self._award_loyalty_points(
                    payment=payment_transaction,
                )

                payment_transaction.loyalty_points_earned = loyalty_points

                await self.repository.save(
                    payment_transaction,
                )

                await self.repository.commit()

                await self.repository.refresh(
                    payment_transaction,
                )
            #
            # Receipt.
            #
            if payment_transaction.status == PaymentStatus.SUCCESSFUL:
                await self._generate_payment_receipt(
                    payment=payment_transaction,
                )

            #
            # Notification.
            #
            if payment_transaction.status == PaymentStatus.PENDING:
                await self._create_payment_notification(
                    payment=payment_transaction,
                    notification_type=NotificationType.PAYMENT_INITIATED,
                    title="Payment Initiated",
                    message=(
                        f"Your payment "
                        f"{payment_transaction.transaction_number} "
                        f"for your parking session has been initiated "
                        f"and is awaiting confirmation."
                    ),
                )
            elif payment_transaction.status == PaymentStatus.SUCCESSFUL:
                await self._create_payment_notification(
                    payment=payment_transaction,
                    notification_type=NotificationType.PAYMENT_SUCCESSFUL,
                    title="Payment Successful",
                    message=(
                        f"Your parking session payment "
                        f"{payment_transaction.transaction_number} "
                        f"of KES {payment_transaction.total_amount} "
                        f"was successful."
                    ),
                )

            return payment_transaction

        except Exception:
            await self.repository.rollback()
            raise

    # ==========================================================
    # Reservation Payments
    # ==========================================================

    async def process_reservation_payment(
        self,
        payment: ReservationPaymentCreate,
    ) -> PaymentTransaction:
        """
        Process payment for a parking reservation.

        Workflow
        --------
        Reservation
            ↓
        Validate Reservation
            ↓
        Validate Amount
            ↓
        Resolve Payment Provider
            ↓
        Process Provider Payment
            ↓
        Create Payment Transaction
            ↓
        Debit Wallet (if wallet payment)
            ↓
        Mark Reservation Paid
            ↓
        Confirm Reservation
            ↓
        Commit Transaction
        """
        if payment.reservation_id is None:
            raise ValueError("Reservation ID is required.")

        #
        # Retrieve reservation.
        #
        reservation = await self.reservation_repository.get_by_id(
            payment.reservation_id,
        )

        if reservation is None:
            raise ValueError("Reservation not found.")

        #
        # Prevent duplicate payments.
        #
        if reservation.is_paid:
            raise ValueError("Reservation has already been paid.")

        #
        # Only CREATED reservations may be paid.
        #
        if reservation.status != ReservationStatus.CREATED:
            raise ValueError("Only CREATED reservations can be paid.")

        #
        # Validate payment amount.
        #
        expected_amount = reservation.estimated_amount.quantize(
            Decimal("0.01"),
        )
        received_amount = payment.total_amount.quantize(Decimal("0.01"))

        await self._validate_loyalty_points_contribution(
            customer_id=payment.customer_id,
            points=payment.loyalty_points_to_redeem,
            expected_amount=expected_amount,
            remaining_amount=received_amount,
        )

        try:
            # ======================================================
            # Resolve Payment Provider
            # ======================================================
            if payment.total_amount > Decimal("0.00"):
                provider = PaymentProviderFactory.get_provider(
                    payment.payment_provider,
                )

                provider_response = await provider.process_payment(
                    payment=payment,
                )

                if not provider_response.success:
                    raise ValueError(
                        provider_response.message
                        or "Payment provider rejected the payment."
                    )

                # ======================================================
                # Create Payment Transaction
                # ======================================================
                payment_transaction = await self._create_payment(
                    payment,
                    provider_response=provider_response,
                )
            else:
                # Full payment is covered by loyalty points.
                payment_transaction = await self._create_payment(
                    payment,
                    status=PaymentStatus.SUCCESSFUL,
                )
                payment_transaction.paid_at = datetime.now(timezone.utc)

            payment_transaction.loyalty_points_redeemed = (
                payment.loyalty_points_to_redeem
            )
            await self.repository.save(payment_transaction)

            # ======================================================
            # Asynchronous Payment Provider
            # ======================================================
            if provider_response.status == PaymentStatus.PENDING:
                reservation.payment_status = ReservationPaymentStatus.PENDING
                reservation.last_payment_transaction = payment_transaction
                reservation.last_payment_transaction_id = payment_transaction.id

                await self.reservation_repository.save(reservation)
                await self.repository.commit()
                await self.repository.refresh(payment_transaction)
                await self.reservation_repository.refresh(reservation)

                await self._create_payment_notification(
                    payment=payment_transaction,
                    notification_type=NotificationType.PAYMENT_INITIATED,
                    title="Payment Initiated",
                    message=(
                        f"Your payment "
                        f"{payment_transaction.transaction_number} "
                        f"for your parking reservation has been initiated "
                        f"and is awaiting confirmation."
                    ),
                )

                return payment_transaction

            # ======================================================
            # Wallet Payment
            # ======================================================
            if payment.payment_method == PaymentMethod.WALLET:
                wallet = await self._get_customer_wallet(payment.customer_id)

                await self.wallet_service.debit_wallet(
                    wallet_id=wallet.id,
                    amount=payment.total_amount,
                    payment_transaction_id=payment_transaction.id,
                    created_by=payment.customer_id,
                    reference=payment_transaction.transaction_number,
                    description="Reservation payment",
                )

            now = datetime.now(timezone.utc)

            # ======================================================
            # Update Reservation
            # ======================================================
            reservation.payment_status = ReservationPaymentStatus.PAID
            reservation.status = ReservationStatus.CONFIRMED
            reservation.confirmed_at = now
            reservation.paid_at = now
            reservation.last_payment_transaction = payment_transaction
            reservation.last_payment_transaction_id = payment_transaction.id

            #
            # Persist reservation.
            #
            await self.reservation_repository.save(reservation)

            #
            # Commit.
            #
            await self.repository.commit()

            #
            # Refresh.
            #
            await self.repository.refresh(payment_transaction)
            await self.reservation_repository.refresh(reservation)

            #
            # Loyalty points redemption.
            #
            if (
                payment_transaction.status == PaymentStatus.SUCCESSFUL
                and payment_transaction.loyalty_points_redeemed > 0
            ):
                await self._redeem_loyalty_points_for_payment(
                    payment=payment_transaction,
                )

            #
            # Loyalty points earned.
            #
            if payment_transaction.status == PaymentStatus.SUCCESSFUL:
                loyalty_points = await self._award_loyalty_points(
                    payment=payment_transaction,
                )

                payment_transaction.loyalty_points_earned = loyalty_points

                await self.repository.save(
                    payment_transaction,
                )

                await self.repository.commit()

                await self.repository.refresh(
                    payment_transaction,
                )

            #
            # Receipt.
            #
            if payment_transaction.status == PaymentStatus.SUCCESSFUL:
                await self._generate_payment_receipt(
                    payment=payment_transaction,
                )

            await self._create_payment_notification(
                payment=payment_transaction,
                notification_type=NotificationType.PAYMENT_SUCCESSFUL,
                title="Payment Successful",
                message=(
                    f"Your reservation payment "
                    f"{payment_transaction.transaction_number} "
                    f"of KES {payment_transaction.total_amount} "
                    f"was successful."
                ),
            )

            return payment_transaction

        except Exception:
            await self.repository.rollback()
            raise

    # ==========================================================
    # M-Pesa Callback
    # ==========================================================

    async def process_mpesa_callback(
        self,
        callback: MpesaCallbackRequest,
    ) -> PaymentTransaction:
        """
        Process an asynchronous Safaricom STK Push callback.

        This completes a previously initiated M-Pesa payment.

        The callback processor is provider-agnostic and
        dispatches the business workflow according to the
        payment purpose.
        """
        stk = callback.body.stk_callback

        print("\n========== CALLBACK ==========")
        print("ResultCode:", stk.result_code)
        print("ResultDesc:", stk.result_desc)
        print("Receipt:", stk.receipt_number)
        print("Amount:", stk.amount)
        print("Phone:", stk.phone_number)
        print("==============================")

        #
        # Retrieve payment transaction.
        #
        payment = await self.repository.get_by_provider_transaction_id(
            stk.checkout_request_id,
        )

        if payment is None:
            raise ValueError("Payment transaction not found.")

        #
        # Duplicate callbacks are safe.
        #
        if payment.status == PaymentStatus.SUCCESSFUL:
            return payment

        if payment.status == PaymentStatus.FAILED:
            return payment

        try:
            now = datetime.now(timezone.utc)

            #
            # Persist the full provider callback.
            #
            payment.provider_response = callback.model_dump(
                by_alias=True,
            )
            payment.provider_status_message = stk.result_desc
            payment.provider_message = stk.result_desc

            #
            # ======================================================
            # PAYMENT FAILED
            # ======================================================
            #
            if stk.result_code != 0:
                payment.status = PaymentStatus.FAILED
                payment.loyalty_points_redeemed = 0

                await self.repository.save(payment)
                await self.repository.commit()
                await self.repository.refresh(payment)

                await self._create_payment_notification(
                    payment=payment,
                    notification_type=NotificationType.PAYMENT_FAILED,
                    title="Payment Failed",
                    message=(
                        f"Your payment {payment.transaction_number} failed. "
                        f"{payment.provider_status_message or 'The payment provider rejected the transaction.'}"
                    ),
                )

                return payment

            #
            # ======================================================
            # PAYMENT SUCCESS
            # ======================================================
            #
            payment.status = PaymentStatus.SUCCESSFUL
            payment.paid_at = now
            payment.receipt_number = stk.receipt_number
            payment.external_reference = stk.receipt_number

            #
            # Persist payment first.
            #
            await self.repository.save(payment)

            #
            # Dispatch business workflow.
            #
            if payment.payment_purpose == PaymentPurpose.RESERVATION:
                await self._complete_reservation_payment(
                    payment=payment,
                    paid_at=now,
                )

            elif payment.payment_purpose == PaymentPurpose.PARKING_SESSION:
                await self._complete_session_payment(
                    payment=payment,
                    paid_at=now,
                )

            elif payment.payment_purpose == PaymentPurpose.WALLET_TOPUP:
                await self._complete_wallet_topup(
                    payment=payment,
                    paid_at=now,
                )

            else:
                raise ValueError(
                    f"Unsupported payment purpose: "
                    f"{payment.payment_purpose}"
                )

            #
            # Commit everything as one transaction.
            #
            await self.repository.commit()

            #
            # Refresh payment.
            #
            await self.repository.refresh(payment)

            #
            # Loyalty points redemption.
            #
            if payment.loyalty_points_redeemed > 0:
                await self._redeem_loyalty_points_for_payment(
                    payment=payment,
                )

            #
            # Loyalty points earned.
            #
            loyalty_points = await self._award_loyalty_points(
                payment=payment,
            )

            payment.loyalty_points_earned = loyalty_points

            await self.repository.save(
                payment,
            )

            await self.repository.commit()

            await self.repository.refresh(
                payment,
            )

            #
            # Receipt.
            #
            await self._generate_payment_receipt(
                payment=payment,
            )

            await self._create_payment_notification(
                payment=payment,
                notification_type=NotificationType.PAYMENT_SUCCESSFUL,
                title="Payment Successful",
                message=(
                    f"Your payment {payment.transaction_number} "
                    f"of KES {payment.total_amount} was successful."
                ),
            )

            return payment

        except Exception:
            await self.repository.rollback()
            raise

    # ==========================================================
    # Internal Completion Helpers
    # ==========================================================

    async def _complete_reservation_payment(
        self,
        *,
        payment: PaymentTransaction,
        paid_at: datetime,
    ) -> None:
        """
        Complete a successful reservation payment.

        This method is called after an asynchronous
        payment provider (e.g. M-Pesa) confirms that
        payment has been received.
        """
        reservation = await self.reservation_repository.get_by_id(
            payment.reservation_id,
        )

        if reservation is None:
            raise ValueError("Reservation not found.")

        reservation.payment_status = ReservationPaymentStatus.PAID
        reservation.status = ReservationStatus.CONFIRMED
        reservation.confirmed_at = paid_at
        reservation.paid_at = paid_at
        reservation.last_payment_transaction = payment
        reservation.last_payment_transaction_id = payment.id

        await self.reservation_repository.save(reservation)
        await self.reservation_repository.refresh(reservation)

    async def _complete_session_payment(
        self,
        *,
        payment: PaymentTransaction,
        paid_at: datetime,
    ) -> None:
        """
        Complete a successful parking session payment.

        This method is called after an asynchronous
        payment provider confirms payment.
        """
        parking_session = await self.session_repository.get_by_id(
            payment.parking_session_id,
        )

        if parking_session is None:
            raise ValueError("Parking session not found.")

        parking_session.status = SessionStatus.COMPLETED
        parking_session.payment_status = SessionPaymentStatus.PAID
        parking_session.paid_amount = payment.total_amount
        parking_session.last_payment_transaction = payment
        parking_session.last_payment_transaction_id = payment.id
        parking_session.paid_at = paid_at

        await self.session_repository.save(parking_session)
        await self.session_repository.refresh(parking_session)


    async def _complete_wallet_topup(
        self,
        *,
        payment: PaymentTransaction,
        paid_at: datetime,
    ) -> None:
        """
        Complete a successful wallet top-up.

        This method is called after an asynchronous
        payment provider (e.g. M-Pesa) confirms that
        payment has been received.
        """

        wallet = await self._get_customer_wallet(
            payment.customer_id,
        )

        await self.wallet_service.credit_wallet(
            wallet_id=wallet.id,
            amount=payment.total_amount,
            payment_transaction_id=payment.id,
            created_by=payment.customer_id,
            description="Wallet Top-up",
            reference=payment.transaction_number,
        )

    # ==========================================================
    # Refund
    # ==========================================================

    async def process_refund(
        self,
        payment: RefundCreate,
    ) -> PaymentTransaction:
        """
        Process a refund transaction.
        """
        if payment.parent_transaction_id is None:
            raise ValueError("Parent transaction ID is required.")

        #
        # Retrieve original payment.
        #
        original_payment = await self.repository.get_by_id(
            payment.parent_transaction_id,
        )

        if original_payment is None:
            raise ValueError("Original payment not found.")

        #
        # Prevent duplicate refunds.
        #
        if original_payment.status == PaymentStatus.REFUNDED:
            raise ValueError("This payment has already been refunded.")

        #
        # Only successful payments may be refunded.
        #
        if original_payment.status != PaymentStatus.SUCCESSFUL:
            raise ValueError("Only SUCCESSFUL payments can be refunded.")

        #
        # Validate refund amount.
        #
        if payment.total_amount > original_payment.total_amount:
            raise ValueError(
                "Refund amount cannot exceed the original payment amount."
            )

        #
        # Customer wallet.
        #
        wallet = await self._get_customer_wallet(original_payment.customer_id)

        try:
            #
            # Create refund payment transaction.
            #
            payment_transaction = await self._create_payment(payment)

            #
            # A refund belongs to the customer of the original payment.
            # RefundCreate may not carry customer_id, so inherit it from
            # the original transaction before creating the notification.
            # This is intentionally scoped to the refund workflow only.
            #
            payment_transaction.customer_id = original_payment.customer_id
            await self.repository.save(payment_transaction)

            #
            # Refund customer's wallet.
            #
            await self.wallet_service.credit_wallet(
                wallet_id=wallet.id,
                amount=payment.total_amount,
                transaction_type=WalletTransactionType.REFUND,
                payment_transaction_id=payment_transaction.id,
                created_by=original_payment.customer_id,
                reference=original_payment.transaction_number,
                description="Payment refund",
            )

            #
            # Update original payment status.
            #
            if payment.total_amount == original_payment.total_amount:
                original_payment.status = PaymentStatus.REFUNDED
            else:
                original_payment.status = PaymentStatus.PARTIALLY_REFUNDED

            await self.repository.save(original_payment)
            await self.repository.commit()
            await self.repository.refresh(payment_transaction)

            await self._create_payment_notification(
                payment=payment_transaction,
                notification_type=NotificationType.PAYMENT_REFUNDED,
                title="Payment Refunded",
                message=(
                    f"Your payment {original_payment.transaction_number} "
                    f"has been refunded for KES {payment_transaction.total_amount}."
                ),
            )

            return payment_transaction

        except Exception:
            await self.repository.rollback()
            raise

    # ==========================================================
    # Reversal
    # ==========================================================

    async def process_reversal(
        self,
        payment: ReversalCreate,
    ) -> PaymentTransaction:
        """
        Process a reversal transaction.
        """
        if payment.parent_transaction_id is None:
            raise ValueError("Parent transaction ID is required.")

        #
        # Retrieve original payment.
        #
        original_payment = await self.repository.get_by_id(
            payment.parent_transaction_id,
        )

        if original_payment is None:
            raise ValueError("Original payment not found.")

        #
        # Prevent duplicate reversal.
        #
        if original_payment.status == PaymentStatus.VOIDED:
            raise ValueError("This payment has already been reversed.")

        #
        # Only successful payments may be reversed.
        #
        if original_payment.status != PaymentStatus.SUCCESSFUL:
            raise ValueError("Only SUCCESSFUL payments can be reversed.")

        #
        # Validate reversal amount.
        #
        if payment.total_amount > original_payment.total_amount:
            raise ValueError(
                "Reversal amount cannot exceed the original payment amount."
            )

        #
        # Customer wallet.
        #
        wallet = await self._get_customer_wallet(original_payment.customer_id)

        try:
            #
            # Create reversal payment transaction.
            #
            payment_transaction = await self._create_payment(payment)

            #
            # Reverse customer's wallet.
            #
            await self.wallet_service.credit_wallet(
                wallet_id=wallet.id,
                amount=payment.total_amount,
                transaction_type=WalletTransactionType.REVERSAL,
                payment_transaction_id=payment_transaction.id,
                created_by=original_payment.customer_id,
                reference=original_payment.transaction_number,
                description="Payment reversal",
            )

            #
            # Update original payment status.
            #
            original_payment.status = PaymentStatus.VOIDED

            await self.repository.save(original_payment)
            await self.repository.commit()
            await self.repository.refresh(payment_transaction)

            return payment_transaction

        except Exception:
            await self.repository.rollback()
            raise

    # ==========================================================
    # Payment Query Operations
    # ==========================================================

    async def get_payment(self, payment_id: int) -> PaymentTransaction | None:
        """
        Retrieve a payment transaction by ID.
        """
        return await self.repository.get_by_id(payment_id)

    async def get_transaction(
        self,
        transaction_number: str,
    ) -> PaymentTransaction | None:
        """
        Retrieve a payment using its transaction number.
        """
        return await self.repository.get_by_transaction_number(transaction_number)

    async def get_receipt(
        self,
        receipt_number: str,
    ) -> PaymentTransaction | None:
        """
        Retrieve a payment using its receipt number.
        """
        return await self.repository.get_by_receipt_number(receipt_number)

    async def get_all_payments(self) -> list[PaymentTransaction]:
        """
        Retrieve all payment transactions.
        """
        return await self.repository.get_all()

    async def get_customer_payments(
        self,
        customer_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PaymentTransaction]:
        """
        Retrieve all payments for a customer.
        """
        return await self.repository.get_customer_payments(
            customer_id=customer_id,
            limit=limit,
            offset=offset,
        )

    async def get_reservation_payments(
        self,
        reservation_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PaymentTransaction]:
        """
        Retrieve all payments for a reservation.
        """
        return await self.repository.get_reservation_payments(
            reservation_id=reservation_id,
            limit=limit,
            offset=offset,
        )

    async def get_session_payments(
        self,
        parking_session_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PaymentTransaction]:
        """
        Retrieve all payments for a parking session.
        """
        return await self.repository.get_session_payments(
            parking_session_id=parking_session_id,
            limit=limit,
            offset=offset,
        )

    async def get_recent_payments(
        self,
        *,
        limit: int = 20,
    ) -> list[PaymentTransaction]:
        """
        Retrieve the most recent payments.
        """
        return await self.repository.get_recent_payments(limit=limit)

    async def get_unreconciled_payments(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PaymentTransaction]:
        """
        Retrieve payments awaiting reconciliation.
        """
        return await self.repository.get_unreconciled_payments(
            limit=limit,
            offset=offset,
        )

    async def payment_exists(self, payment_id: int) -> bool:
        """
        Determine whether a payment exists.
        """
        return await self.repository.exists(payment_id)

    # ==========================================================
    # Payment Statistics Operations
    # ==========================================================

    async def total_payments(self) -> int:
        """
        Return total payment count.
        """
        return await self.repository.count_all()

    async def total_successful_payments(self) -> int:
        """
        Return total successful payments.
        """
        return await self.repository.count_by_status(PaymentStatus.SUCCESSFUL)

    async def total_pending_payments(self) -> int:
        """
        Return total pending payments.
        """
        return await self.repository.count_by_status(PaymentStatus.PENDING)

    async def total_failed_payments(self) -> int:
        """
        Return total failed payments.
        """
        return await self.repository.count_by_status(PaymentStatus.FAILED)

    async def total_revenue(self) -> Decimal:
        """
        Return total successful revenue.
        """
        return await self.repository.total_revenue()

    async def total_refunds(self) -> Decimal:
        """
        Return total refunded amount.
        """
        return await self.repository.total_refunds()

    async def total_customer_payments(self, customer_id: int) -> int:
        """
        Return payment count for a customer.
        """
        return await self.repository.count_customer_payments(customer_id)

    async def total_customer_revenue(self, customer_id: int) -> Decimal:
        """
        Return total revenue for a customer.
        """
        return await self.repository.total_customer_revenue(customer_id)

    async def unreconciled_count(self) -> int:
        """
        Return unreconciled payment count.
        """
        return await self.repository.count_unreconciled()