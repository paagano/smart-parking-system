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
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    PaymentMethod,
    PaymentStatus,
    ReservationPaymentStatus,
    ReservationStatus,
    SessionPaymentStatus,
    SessionStatus,
    WalletTransactionType,
)

from app.models.payment_transaction import (
    PaymentTransaction,
)

from app.models.wallet import (
    Wallet,
)

from app.repositories.payment_repository import (
    PaymentRepository,
)

from app.repositories.parking_reservation_repository import (
    ParkingReservationRepository,
)

from app.repositories.parking_session_repository import (
    ParkingSessionRepository,
)

from app.schemas.payment import (
    PaymentCreate,
    RefundCreate,
    ReservationPaymentCreate,
    SessionPaymentCreate,
    WalletTopUpCreate,
)

from app.services.wallet_service import (
    WalletService,
)


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
        wallet_service: WalletService,
    ) -> None:

        self.db = db

        self.repository = repository

        self.reservation_repository = (
            reservation_repository
        )

        self.session_repository = (
            session_repository
        )

        #
        # Wallet integration.
        #
        # Wallet operations are delegated to WalletService.
        #
        self.wallet_service = (
            wallet_service
        )

    # ==========================================================
    # Internal Helpers
    # ==========================================================

    def _generate_transaction_number(
        self,
    ) -> str:
        """
        Generate a unique transaction number.

        Example
        -------
        PAY-20260802-143255-A3F9C2
        """

        timestamp = datetime.now(
            timezone.utc,
        ).strftime(
            "%Y%m%d-%H%M%S",
        )

        suffix = (
            uuid.uuid4()
            .hex[:6]
            .upper()
        )

        return (
            f"PAY-{timestamp}-{suffix}"
        )

    @staticmethod
    def _money(
        value: Decimal,
    ) -> Decimal:
        """
        Normalize a monetary value to two decimal places.
        """

        return value.quantize(
            Decimal("0.01"),
        )

    async def _get_customer_wallet(
        self,
        customer_id: int,
    ) -> Wallet:
        """
        Retrieve the customer's wallet.

        Wallet lookup is delegated to WalletService.
        """

        return await self.wallet_service.get_wallet_by_customer(
            customer_id,
        )

    # ==========================================================
    # Internal Payment Creator
    # ==========================================================

    async def _create_payment(
        self,
        payment: PaymentCreate,
        *,
        status: PaymentStatus = PaymentStatus.SUCCESSFUL,
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
            raise ValueError(
                "Subtotal amount cannot be negative."
            )

        if payment.tax_amount < 0:
            raise ValueError(
                "Tax amount cannot be negative."
            )

        if payment.total_amount < 0:
            raise ValueError(
                "Total amount cannot be negative."
            )

        payment_transaction = PaymentTransaction(

            # ==================================================
            # Relationships
            # ==================================================

            reservation_id=getattr(
                payment,
                "reservation_id",
                None,
            ),

            parking_session_id=getattr(
                payment,
                "parking_session_id",
                None,
            ),

            customer_id=getattr(
                payment,
                "customer_id",
                None,
            ),

            parent_transaction_id=getattr(
                payment,
                "parent_transaction_id",
                None,
            ),

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

            # ==================================================
            # Audit
            # ==================================================

            notes=payment.notes,

            status=status,

            paid_at=(
                datetime.now(timezone.utc)
                if status == PaymentStatus.SUCCESSFUL
                else None
            ),
        )

        await self.repository.save(
            payment_transaction,
        )

        await self.repository.refresh(
            payment_transaction,
        )

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
            raise ValueError(
                "Customer ID is required."
            )

        #
        # Retrieve customer's wallet.
        #
        wallet = await self._get_customer_wallet(
            payment.customer_id,
        )

        try:

            #
            # Create payment transaction.
            #
            payment_transaction = (
                await self._create_payment(
                    payment,
                )
            )

            #
            # Credit customer wallet.
            #
            await self.wallet_service.credit_wallet(

                wallet_id=wallet.id,

                amount=payment.total_amount,

                payment_transaction_id=payment_transaction.id,

                created_by=payment.customer_id,

                description=(
                    "Wallet Top-up"
                ),

                reference=(
                    payment_transaction.transaction_number
                ),
            )

            #
            # Commit payment transaction.
            #
            await self.repository.commit()

            #
            # Refresh payment.
            #
            await self.repository.refresh(
                payment_transaction,
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
            raise ValueError(
                "Parking session ID is required."
            )

        #
        # Retrieve parking session.
        #
        parking_session = (
            await self.session_repository.get_by_id(
                payment.parking_session_id,
            )
        )

        if parking_session is None:
            raise ValueError(
                "Parking session not found."
            )

        #
        # Prevent duplicate payments.
        #
        if parking_session.is_paid:
            raise ValueError(
                "Parking session has already been paid."
            )

        #
        # Only completed sessions may be paid.
        #
        if parking_session.status != SessionStatus.COMPLETED:
            raise ValueError(
                "Only COMPLETED parking sessions can be paid."
            )

        #
        # Validate payment amount.
        #
        expected_amount = (
            parking_session.calculated_amount.quantize(
                Decimal("0.01"),
            )
        )

        received_amount = (
            payment.total_amount.quantize(
                Decimal("0.01"),
            )
        )

        if expected_amount != received_amount:
            raise ValueError(
                "Payment amount does not match the calculated parking fee."
            )

        try:

            #
            # Create payment transaction.
            #
            payment_transaction = (
                await self._create_payment(
                    payment,
                )
            )

            #
            # Wallet payment.
            #
            if (
                payment.payment_method
                == PaymentMethod.WALLET
            ):

                wallet = await self._get_customer_wallet(
                    payment.customer_id,
                )

                await self.wallet_service.debit_wallet(

                    wallet_id=wallet.id,

                    amount=payment.total_amount,

                    payment_transaction_id=payment_transaction.id,

                    created_by=payment.customer_id,

                    reference=payment_transaction.transaction_number,

                    description=(
                        "Parking session payment"
                    ),
                )

            #
            # Update parking session.
            #
            parking_session.payment_status = (
                SessionPaymentStatus.PAID
            )

            parking_session.paid_amount = (
                payment_transaction.total_amount
            )

            parking_session.last_payment_transaction_id = (
                payment_transaction.id
            )

            parking_session.paid_at = (
                payment_transaction.paid_at
            )

            #
            # Persist session updates.
            #
            await self.session_repository.save(
                parking_session,
            )

            #
            # Commit everything.
            #
            await self.repository.commit()

            #
            # Refresh entities.
            #
            await self.repository.refresh(
                payment_transaction,
            )

            await self.session_repository.refresh(
                parking_session,
            )

            return payment_transaction

        except Exception:

            await self.repository.rollback()

            raise

    # ==========================================================
    # Reservation Payment
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
        Create Payment
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
            raise ValueError(
                "Reservation ID is required."
            )

        #
        # Retrieve reservation.
        #
        reservation = (
            await self.reservation_repository.get_by_id(
                payment.reservation_id,
            )
        )

        if reservation is None:
            raise ValueError(
                "Reservation not found."
            )

        #
        # Prevent duplicate payments.
        #
        if reservation.is_paid:
            raise ValueError(
                "Reservation has already been paid."
            )

        #
        # Only CREATED reservations may be paid.
        #
        if reservation.status != ReservationStatus.CREATED:
            raise ValueError(
                "Only CREATED reservations can be paid."
            )

        #
        # Validate payment amount.
        #
        expected_amount = (
            reservation.estimated_amount.quantize(
                Decimal("0.01"),
            )
        )

        received_amount = (
            payment.total_amount.quantize(
                Decimal("0.01"),
            )
        )

        if expected_amount != received_amount:
            raise ValueError(
                "Payment amount does not match the reservation amount."
            )

        try:

            #
            # Create payment transaction.
            #
            payment_transaction = (
                await self._create_payment(
                    payment,
                )
            )

            #
            # Wallet payment.
            #
            if (
                payment.payment_method
                == PaymentMethod.WALLET
            ):

                wallet = await self._get_customer_wallet(
                    payment.customer_id,
                )

                await self.wallet_service.debit_wallet(

                    wallet_id=wallet.id,

                    amount=payment.total_amount,

                    payment_transaction_id=payment_transaction.id,

                    created_by=payment.customer_id,

                    reference=payment_transaction.transaction_number,

                    description=(
                        "Reservation payment"
                    ),
                )

            now = datetime.now(
                timezone.utc,
            )

            #
            # Update reservation.
            #
            reservation.payment_status = (
                ReservationPaymentStatus.PAID
            )

            reservation.status = (
                ReservationStatus.CONFIRMED
            )

            reservation.confirmed_at = now

            reservation.paid_at = now

            reservation.last_payment_transaction = (
                payment_transaction
            )

            reservation.last_payment_transaction_id = (
                payment_transaction.id
            )

            #
            # Persist reservation changes.
            #
            await self.reservation_repository.save(
                reservation,
            )

            #
            # Commit transaction.
            #
            await self.repository.commit()

            #
            # Refresh entities.
            #
            await self.repository.refresh(
                payment_transaction,
            )

            await self.reservation_repository.refresh(
                reservation,
            )

            return payment_transaction

        except Exception:

            await self.repository.rollback()

            raise

        # ==========================================================
    # Wallet Top-up
    # ==========================================================

    async def process_wallet_topup(
        self,
        payment: WalletTopUpCreate,
    ) -> PaymentTransaction:
        """
        Process a wallet top-up.
        """

        if payment.customer_id is None:
            raise ValueError(
                "Customer ID is required."
            )

        #
        # Retrieve customer's wallet.
        #
        wallet = await self._get_customer_wallet(
            payment.customer_id,
        )

        try:

            #
            # Create payment transaction.
            #
            payment_transaction = (
                await self._create_payment(
                    payment,
                )
            )

            #
            # Credit customer's wallet.
            #
            await self.wallet_service.credit_wallet(

                wallet_id=wallet.id,

                amount=payment.total_amount,

                payment_transaction_id=payment_transaction.id,

                created_by=payment.customer_id,

                reference=payment_transaction.transaction_number,

                description="Wallet top-up",

            )

            #
            # Commit payment transaction.
            #
            await self.repository.commit()

            #
            # Refresh payment transaction.
            #
            await self.repository.refresh(
                payment_transaction,
            )

            return payment_transaction

        except Exception:

            await self.repository.rollback()

            raise

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
            raise ValueError(
                "Parent transaction ID is required."
            )

        #
        # Retrieve original payment.
        #
        original_payment = await self.repository.get_by_id(
            payment.parent_transaction_id,
        )

        if original_payment is None:
            raise ValueError(
                "Original payment not found."
            )

        #
        # Customer wallet.
        #
        wallet = await self._get_customer_wallet(
            original_payment.customer_id,
        )

        try:

            #
            # Create refund payment transaction.
            #
            payment_transaction = (
                await self._create_payment(
                    payment,
                )
            )

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

            await self.repository.commit()

            await self.repository.refresh(
                payment_transaction,
            )

            return payment_transaction

        except Exception:

            await self.repository.rollback()

            raise