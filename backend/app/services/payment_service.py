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

from app.models.enums import PaymentStatus, ReservationPaymentStatus, ReservationStatus, SessionPaymentStatus, SessionStatus
from app.models.payment_transaction import PaymentTransaction
from app.repositories.payment_repository import PaymentRepository
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


class PaymentService:
    """
    Business logic for payment transactions.
    """
    
    def __init__(
        self,
        repository: PaymentRepository,
        reservation_repository: ParkingReservationRepository,
        session_repository: ParkingSessionRepository,
    ) -> None:

        self.repository = repository

        self.reservation_repository = (
            reservation_repository
        )

        self.session_repository = (
            session_repository
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

    # ==========================================================
    # Internal Payment Creator
    # ==========================================================

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        """
        Normalize a monetary value to two decimal places.

        Ensures consistent comparison and persistence of
        financial values throughout the payment service.
        """
        return value.quantize(Decimal("0.01"))

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
        # Validate amounts are not negative
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

        #
        # Persist the entity.
        #
        # BaseRepository.save() performs:
        #   - add()
        #   - flush()
        #   - refresh()
        #
        await self.repository.save(payment_transaction)

        #
        # Ensure we have the latest database state.
        #
        await self.repository.refresh(payment_transaction)

        #
        # A persisted payment must always have a primary key.
        #
        if payment_transaction.id is None:
            raise RuntimeError(
                "Failed to generate PaymentTransaction primary key."
            )

        return payment_transaction

    # ==========================================================
    # Basic Retrieval
    # ==========================================================

    async def get_payment(self, payment_id: int) -> PaymentTransaction | None:
        """
        Retrieve a payment by its ID.
        """
        return await self.repository.get_by_id(payment_id)

    async def get_all_payments(self) -> list[PaymentTransaction]:
        """
        Retrieve all payment transactions.
        """
        return await self.repository.get_all()

    async def payment_exists(self, payment_id: int) -> bool:
        """
        Determine whether a payment exists.
        """
        return await self.repository.exists(payment_id)

    # ==========================================================
    # Transaction Lookups
    # ==========================================================

    async def get_transaction(
        self,
        transaction_number: str,
    ) -> PaymentTransaction | None:
        """
        Retrieve a payment using its transaction number.
        """
        return await self.repository.get_by_transaction_number(
            transaction_number,
        )

    async def get_provider_transaction(
        self,
        provider_transaction_id: str,
    ) -> PaymentTransaction | None:
        """
        Retrieve a payment using the provider transaction ID.
        """
        return await self.repository.get_by_provider_transaction_id(
            provider_transaction_id,
        )

    async def get_external_reference(
        self,
        external_reference: str,
    ) -> PaymentTransaction | None:
        """
        Retrieve a payment using an external reference.
        """
        return await self.repository.get_by_external_reference(
            external_reference,
        )

    async def get_receipt(
        self,
        receipt_number: str,
    ) -> PaymentTransaction | None:
        """
        Retrieve a payment using its receipt number.
        """
        return await self.repository.get_by_receipt_number(receipt_number)

    # ==========================================================
    # Customer Queries
    # ==========================================================

    async def get_customer_payments(
        self,
        customer_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PaymentTransaction]:
        """
        Retrieve payment history for a customer.
        """
        return await self.repository.get_customer_payments(
            customer_id=customer_id,
            limit=limit,
            offset=offset,
        )

    # ==========================================================
    # Reservation Queries
    # ==========================================================

    async def get_reservation_payments(
        self,
        reservation_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PaymentTransaction]:
        """
        Retrieve payments belonging to a reservation.
        """
        return await self.repository.get_reservation_payments(
            reservation_id=reservation_id,
            limit=limit,
            offset=offset,
        )

    # ==========================================================
    # Parking Session Queries
    # ==========================================================

    async def get_session_payments(
        self,
        parking_session_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PaymentTransaction]:
        """
        Retrieve payments belonging to a parking session.
        """
        return await self.repository.get_session_payments(
            parking_session_id=parking_session_id,
            limit=limit,
            offset=offset,
        )

    # ==========================================================
    # Refund Queries
    # ==========================================================

    async def get_child_transactions(
        self,
        parent_transaction_id: int,
    ) -> list[PaymentTransaction]:
        """
        Retrieve child transactions.

        Example
        -------
        Original Payment
              ↓
           Refund
              ↓
      Refund Adjustment
        """
        return await self.repository.get_child_transactions(
            parent_transaction_id,
        )

    # ==========================================================
    # Reconciliation
    # ==========================================================

    async def get_unreconciled_payments(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PaymentTransaction]:
        """
        Retrieve unreconciled payment transactions.
        """
        return await self.repository.get_unreconciled_payments(
            limit=limit,
            offset=offset,
        )

    async def mark_reconciled(self, payment_id: int) -> PaymentTransaction:
        """
        Mark a payment as reconciled.
        """
        payment = await self.repository.get_by_id(payment_id)

        if payment is None:
            raise ValueError("Payment not found.")

        payment.reconciled = True
        payment.reconciled_at = datetime.now(timezone.utc)
        
        await self.repository.save(payment)
        await self.repository.commit()
        await self.repository.refresh(payment)
        
        return payment

    # ==========================================================
    # Recent Payments
    # ==========================================================

    async def get_recent_payments(
        self,
        *,
        limit: int = 20,
    ) -> list[PaymentTransaction]:
        """
        Retrieve recently created payment transactions.
        """
        return await self.repository.get_recent_payments(limit=limit)

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
        Mark Reservation Paid
            ↓
        Confirm Reservation
            ↓
        Commit Transaction
        """
        if payment.reservation_id is None:
            raise ValueError("Reservation ID is required.")

        #
        # Retrieve reservation
        #
        reservation = await self.reservation_repository.get_by_id(
            payment.reservation_id,
        )

        if reservation is None:
            raise ValueError("Reservation not found.")

        #
        # Prevent duplicate payments
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
        expected_amount = reservation.estimated_amount.quantize(Decimal("0.01"))
        received_amount = payment.total_amount.quantize(Decimal("0.01"))

        if expected_amount != received_amount:
            raise ValueError(
                "Payment amount does not match the reservation amount."
            )

        try:
            #
            # Create the payment transaction.
            #
            payment_transaction = await self._create_payment(payment)

            now = datetime.now(timezone.utc)

            #
            # Update reservation.
            #
            reservation.payment_status = ReservationPaymentStatus.PAID
            reservation.status = ReservationStatus.CONFIRMED
            reservation.confirmed_at = now
            reservation.paid_at = now

            #
            # Associate the payment using both the ORM relationship and ID field.
            #
            reservation.last_payment_transaction = payment_transaction
            reservation.last_payment_transaction_id = payment_transaction.id

            #
            # Persist reservation updates.
            #
            await self.reservation_repository.save(reservation)

            #
            # Commit everything atomically.
            #
            await self.repository.commit()

            #
            # Refresh ORM entities to get latest state.
            #
            await self.repository.refresh(payment_transaction)
            await self.reservation_repository.refresh(reservation)

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
            # Commit everything together.
            #
            await self.repository.commit()

            #
            # Refresh ORM entities.
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
    # Wallet Top-up
    # ==========================================================

    async def process_wallet_topup(
        self,
        payment: WalletTopUpCreate,
    ) -> PaymentTransaction:
        """
        Process a wallet top-up.
        """

        #
        # Future
        #
        # - Credit customer wallet
        # - Generate receipt
        # - Notify customer
        #

        return await self._create_payment(payment)

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
        # Future
        #
        # - Validate original payment
        # - Debit wallet if applicable
        # - Generate refund receipt
        # - Notify customer
        #

        return await self._create_payment(payment)

    # ==========================================================
    # Statistics
    # ==========================================================

    async def total_payments(self) -> int:
        """
        Return the total number of payments.
        """
        return await self.repository.count_all()

    async def total_successful_payments(self) -> int:
        """
        Return the total number of successful payments.
        """
        return await self.repository.count_by_status(PaymentStatus.SUCCESSFUL)

    async def total_pending_payments(self) -> int:
        """
        Return the total number of pending payments.
        """
        return await self.repository.count_by_status(PaymentStatus.PENDING)

    async def total_failed_payments(self) -> int:
        """
        Return the total number of failed payments.
        """
        return await self.repository.count_by_status(PaymentStatus.FAILED)

    async def total_customer_payments(self, customer_id: int) -> int:
        """
        Return the number of payments made by a customer.
        """
        return await self.repository.count_customer_payments(customer_id)

    # ==========================================================
    # Revenue
    # ==========================================================

    async def total_revenue(self) -> Decimal:
        """
        Calculate total successful revenue.
        """
        return await self.repository.total_revenue()

    async def total_customer_revenue(self, customer_id: int) -> Decimal:
        """
        Calculate lifetime customer spend.
        """
        return await self.repository.total_customer_revenue(customer_id)

    async def total_refunds(self) -> Decimal:
        """
        Calculate total refunded amount.
        """
        return await self.repository.total_refunds()

    # ==========================================================
    # Reconciliation
    # ==========================================================

    async def unreconciled_count(self) -> int:
        """
        Return the number of unreconciled payments.
        """
        return await self.repository.count_unreconciled()