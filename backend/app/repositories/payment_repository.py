"""
Repository for Payment Transactions.

Responsible for persistence and retrieval of payment
transactions.

The repository intentionally contains NO business logic.

Business rules belong in the Payment Service.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    PaymentStatus,
    PaymentType,
)
from app.models.payment_transaction import (
    PaymentTransaction,
)
from app.repositories.base_repository import (
    BaseRepository,
)


class PaymentRepository(
    BaseRepository[PaymentTransaction],
):
    """
    Repository for Payment Transactions.
    """

    def __init__(
        self,
        db: AsyncSession,
    ) -> None:
        super().__init__(
            db=db,
            model=PaymentTransaction,
        )

    # ==========================================================
    # Basic Retrieval
    # ==========================================================

    async def get_by_id(
        self,
        payment_id: int,
    ) -> PaymentTransaction | None:
        """
        Retrieve a payment by ID.
        """

        statement = (
            select(
                PaymentTransaction,
            )
            .where(
                PaymentTransaction.id == payment_id,
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    async def get_all(
        self,
    ) -> list[PaymentTransaction]:
        """
        Retrieve all payment transactions.
        """

        statement = (
            select(
                PaymentTransaction,
            )
            .order_by(
                PaymentTransaction.created_at.desc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return list(
            result.scalars().all(),
        )

    async def exists(
        self,
        payment_id: int,
    ) -> bool:
        """
        Determine whether a payment exists.
        """

        payment = await self.get_by_id(
            payment_id,
        )

        return payment is not None

    # ==========================================================
    # Transaction Number
    # ==========================================================

    async def get_by_transaction_number(
        self,
        transaction_number: str,
    ) -> PaymentTransaction | None:
        """
        Retrieve a payment using the internal
        transaction number.
        """

        statement = (
            select(
                PaymentTransaction,
            )
            .where(
                PaymentTransaction.transaction_number
                == transaction_number,
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # External References
    # ==========================================================

    async def get_by_provider_transaction_id(
        self,
        provider_transaction_id: str,
    ) -> PaymentTransaction | None:
        """
        Retrieve payment using the provider
        transaction ID.

        Example:
            M-Pesa CheckoutRequestID
            Visa Transaction ID
        """

        statement = (
            select(
                PaymentTransaction,
            )
            .where(
                PaymentTransaction.provider_transaction_id
                == provider_transaction_id,
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    async def get_by_external_reference(
        self,
        external_reference: str,
    ) -> PaymentTransaction | None:
        """
        Retrieve payment using an external reference.
        """

        statement = (
            select(
                PaymentTransaction,
            )
            .where(
                PaymentTransaction.external_reference
                == external_reference,
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Idempotency
    # ==========================================================

    async def get_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> PaymentTransaction | None:
        """
        Prevent duplicate payment creation.
        """

        statement = (
            select(
                PaymentTransaction,
            )
            .where(
                PaymentTransaction.idempotency_key
                == idempotency_key,
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Status Queries
    # ==========================================================

    async def get_by_status(
        self,
        status: PaymentStatus,
    ) -> list[PaymentTransaction]:
        """
        Retrieve payments by status.
        """

        statement = (
            select(
                PaymentTransaction,
            )
            .where(
                PaymentTransaction.status == status,
            )
            .order_by(
                PaymentTransaction.created_at.desc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return list(
            result.scalars().all(),
        )

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

        statement = (
            select(
                PaymentTransaction,
            )
            .where(
                PaymentTransaction.customer_id == customer_id,
            )
            .order_by(
                PaymentTransaction.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(
            statement,
        )

        return list(
            result.scalars().all(),
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
        Retrieve all payments belonging to
        a reservation.
        """

        statement = (
            select(
                PaymentTransaction,
            )
            .where(
                PaymentTransaction.reservation_id
                == reservation_id,
            )
            .order_by(
                PaymentTransaction.created_at.asc(),
            )
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(
            statement,
        )

        return list(
            result.scalars().all(),
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
        Retrieve all payments for a parking session.
        """

        statement = (
            select(
                PaymentTransaction,
            )
            .where(
                PaymentTransaction.parking_session_id
                == parking_session_id,
            )
            .order_by(
                PaymentTransaction.created_at.asc(),
            )
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(
            statement,
        )

        return list(
            result.scalars().all(),
        )

    # ==========================================================
    # Receipt Queries
    # ==========================================================

    async def get_by_receipt_number(
        self,
        receipt_number: str,
    ) -> PaymentTransaction | None:
        """
        Retrieve payment using receipt number.
        """

        statement = (
            select(
                PaymentTransaction,
            )
            .where(
                PaymentTransaction.receipt_number
                == receipt_number,
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Refund Queries
    # ==========================================================

    async def get_child_transactions(
        self,
        parent_transaction_id: int,
    ) -> list[PaymentTransaction]:
        """
        Retrieve all child transactions.

        Example:

            Original Payment

                    ↓

            Refund

                    ↓

            Refund Adjustment
        """

        statement = (
            select(
                PaymentTransaction,
            )
            .where(
                PaymentTransaction.parent_transaction_id
                == parent_transaction_id,
            )
            .order_by(
                PaymentTransaction.created_at.asc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return list(
            result.scalars().all(),
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
        Retrieve payments awaiting reconciliation.
        """

        statement = (
            select(
                PaymentTransaction,
            )
            .where(
                PaymentTransaction.is_reconciled.is_(False),
            )
            .order_by(
                PaymentTransaction.created_at.asc(),
            )
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(
            statement,
        )

        return list(
            result.scalars().all(),
        )

    # ==========================================================
    # Recent Payments
    # ==========================================================

    async def get_recent_payments(
        self,
        *,
        limit: int = 20,
    ) -> list[PaymentTransaction]:
        """
        Retrieve the most recent payments.
        """

        statement = (
            select(
                PaymentTransaction,
            )
            .order_by(
                PaymentTransaction.created_at.desc(),
            )
            .limit(limit)
        )

        result = await self.db.execute(
            statement,
        )

        return list(
            result.scalars().all(),
        )

        # ==========================================================
    # Counts
    # ==========================================================

    async def count_all(
        self,
    ) -> int:
        """
        Count all payment transactions.
        """

        statement = (
            select(
                func.count(
                    PaymentTransaction.id,
                )
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one()

    async def count_by_status(
        self,
        status: PaymentStatus,
    ) -> int:
        """
        Count payments by status.
        """

        statement = (
            select(
                func.count(
                    PaymentTransaction.id,
                )
            )
            .where(
                PaymentTransaction.status == status,
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one()

    async def count_customer_payments(
        self,
        customer_id: int,
    ) -> int:
        """
        Count payments made by a customer.
        """

        statement = (
            select(
                func.count(
                    PaymentTransaction.id,
                )
            )
            .where(
                PaymentTransaction.customer_id == customer_id,
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one()

    # ==========================================================
    # Revenue
    # ==========================================================

    async def total_revenue(
        self,
    ) -> Decimal:
        """
        Calculate total successful revenue.
        """

        statement = (
            select(
                func.coalesce(
                    func.sum(
                        PaymentTransaction.total_amount,
                    ),
                    0,
                )
            )
            .where(
                PaymentTransaction.status
                == PaymentStatus.SUCCESSFUL,
            )
        )

        result = await self.db.execute(
            statement,
        )

        value = result.scalar_one()

        return Decimal(value or 0)

    async def total_customer_revenue(
        self,
        customer_id: int,
    ) -> Decimal:
        """
        Calculate total revenue
        generated by a customer.
        """

        statement = (
            select(
                func.coalesce(
                    func.sum(
                        PaymentTransaction.total_amount,
                    ),
                    0,
                )
            )
            .where(
                PaymentTransaction.customer_id
                == customer_id,
                PaymentTransaction.status
                == PaymentStatus.SUCCESSFUL,
            )
        )

        result = await self.db.execute(
            statement,
        )

        return Decimal(
            result.scalar_one(),
        )

    async def total_refunds(
        self,
    ) -> Decimal:
        """
        Calculate total refunded amount.
        """

        statement = (
            select(
                func.coalesce(
                    func.sum(
                        PaymentTransaction.total_amount,
                    ),
                    0,
                )
            )
            .where(
                PaymentTransaction.payment_type
                == PaymentType.REFUND,
            )
        )

        result = await self.db.execute(
            statement,
        )

        return Decimal(
            result.scalar_one(),
        )

    # ==========================================================
    # Reconciliation
    # ==========================================================

    async def count_unreconciled(
        self,
    ) -> int:
        """
        Count unreconciled payments.
        """

        statement = (
            select(
                func.count(
                    PaymentTransaction.id,
                )
            )
            .where(
                PaymentTransaction.is_reconciled.is_(False),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one()

    # ==========================================================
    # Utility
    # ==========================================================

    async def mark_reconciled(
        self,
        payment: PaymentTransaction,
    ) -> PaymentTransaction:
        """
        Mark a payment as reconciled.

        NOTE:
        This method does not commit the transaction.
        The calling service owns the transaction boundary.
        """

        payment.is_reconciled = True

        await self.save(
            payment,
        )

        return payment

        # ==========================================================
    # Retrieval Operations
    # ==========================================================

    async def get_by_id(
        self,
        payment_id: int,
    ) -> PaymentTransaction:
        """
        Retrieve a payment transaction by ID.
        """

        payment = await self.repository.get_by_id(
            payment_id,
        )

        if payment is None:
            raise ValueError(
                "Payment transaction not found."
            )

        return payment

    async def get_by_transaction_number(
        self,
        transaction_number: str,
    ) -> PaymentTransaction:
        """
        Retrieve a payment transaction using its
        internal transaction number.
        """

        payment = await (
            self.repository.get_by_transaction_number(
                transaction_number,
            )
        )

        if payment is None:
            raise ValueError(
                "Payment transaction not found."
            )

        return payment

    async def get_by_receipt_number(
        self,
        receipt_number: str,
    ) -> PaymentTransaction:
        """
        Retrieve a payment using its receipt number.
        """

        payment = await (
            self.repository.get_by_receipt_number(
                receipt_number,
            )
        )

        if payment is None:
            raise ValueError(
                "Receipt not found."
            )

        return payment

    async def get_by_provider_transaction_id(
        self,
        provider_transaction_id: str,
    ) -> PaymentTransaction:
        """
        Retrieve a payment using the external
        provider transaction identifier.
        """

        payment = await (
            self.repository.get_by_provider_transaction_id(
                provider_transaction_id,
            )
        )

        if payment is None:
            raise ValueError(
                "Payment transaction not found."
            )

        return payment

    async def get_by_external_reference(
        self,
        external_reference: str,
    ) -> PaymentTransaction:
        """
        Retrieve a payment using its external
        reference.
        """

        payment = await (
            self.repository.get_by_external_reference(
                external_reference,
            )
        )

        if payment is None:
            raise ValueError(
                "Payment transaction not found."
            )

        return payment

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

        return await (
            self.repository.get_customer_payments(
                customer_id=customer_id,
                limit=limit,
                offset=offset,
            )
        )

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

        return await (
            self.repository.get_reservation_payments(
                reservation_id=reservation_id,
                limit=limit,
                offset=offset,
            )
        )

    async def get_session_payments(
        self,
        parking_session_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PaymentTransaction]:
        """
        Retrieve payments belonging to a parking
        session.
        """

        return await (
            self.repository.get_session_payments(
                parking_session_id=parking_session_id,
                limit=limit,
                offset=offset,
            )
        )

    async def get_recent_payments(
        self,
        *,
        limit: int = 20,
    ) -> list[PaymentTransaction]:
        """
        Retrieve the most recent payments.
        """

        return await (
            self.repository.get_recent_payments(
                limit=limit,
            )
        )

    async def get_unreconciled_payments(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PaymentTransaction]:
        """
        Retrieve payments awaiting reconciliation.
        """

        return await (
            self.repository.get_unreconciled_payments(
                limit=limit,
                offset=offset,
            )
        )

    async def get_child_transactions(
        self,
        parent_transaction_id: int,
    ) -> list[PaymentTransaction]:
        """
        Retrieve child payment transactions.

        Typical example:

            Payment
                ↓
            Refund
                ↓
            Refund Adjustment
        """

        return await (
            self.repository.get_child_transactions(
                parent_transaction_id,
            )
        )

    async def payment_exists(
        self,
        payment_id: int,
    ) -> bool:
        """
        Determine whether a payment exists.
        """

        return await self.repository.exists(
            payment_id,
        )

    # ==========================================================
    # Validation Helpers
    # ==========================================================

    @staticmethod
    def _validate_amount(
        amount: Decimal,
    ) -> None:
        """
        Ensure the payment amount is valid.
        """

        if amount <= Decimal("0.00"):
            raise ValueError(
                "Payment amount must be greater than zero."
            )

    @staticmethod
    def _ensure_completed(
        payment: PaymentTransaction,
    ) -> None:
        """
        Ensure the payment completed successfully.
        """

        if payment.status != PaymentStatus.SUCCESSFUL:
            raise ValueError(
                "Payment has not completed successfully."
            )

    @staticmethod
    def _ensure_not_refunded(
        payment: PaymentTransaction,
    ) -> None:
        """
        Prevent duplicate refunds.
        """

        if payment.payment_type == PaymentType.REFUND:
            raise ValueError(
                "Payment has already been refunded."
            )