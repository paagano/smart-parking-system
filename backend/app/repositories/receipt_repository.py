"""
Repository for Receipts.

Responsible for persistence and retrieval of Receipt records.

The repository intentionally contains NO business logic.

Business rules belong in the Receipt Service.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ReceiptStatus
from app.models.receipt import Receipt
from app.repositories.base_repository import BaseRepository


class ReceiptRepository(
    BaseRepository[Receipt],
):
    """
    Repository for Receipt records.
    """

    def __init__(
        self,
        db: AsyncSession,
    ) -> None:
        super().__init__(
            db=db,
            model=Receipt,
        )

    # ==========================================================
    # Basic Retrieval
    # ==========================================================

    async def get_by_id(
        self,
        receipt_id: int,
    ) -> Receipt | None:
        """
        Retrieve a receipt by ID.
        """

        statement = (
            select(
                Receipt,
            )
            .where(
                Receipt.id == receipt_id,
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    async def get_all(
        self,
    ) -> list[Receipt]:
        """
        Retrieve all receipts.

        Results are ordered from newest to oldest.
        """

        statement = (
            select(
                Receipt,
            )
            .order_by(
                Receipt.created_at.desc(),
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
        receipt_id: int,
    ) -> bool:
        """
        Determine whether a receipt exists.
        """

        receipt = await self.get_by_id(
            receipt_id,
        )

        return receipt is not None

    # ==========================================================
    # Receipt Number
    # ==========================================================

    async def get_by_receipt_number(
        self,
        receipt_number: str,
    ) -> Receipt | None:
        """
        Retrieve a receipt using its public receipt number.
        """

        statement = (
            select(
                Receipt,
            )
            .where(
                Receipt.receipt_number == receipt_number,
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Verification
    # ==========================================================

    async def get_by_verification_token(
        self,
        verification_token: str,
    ) -> Receipt | None:
        """
        Retrieve a receipt using its verification token.

        This method will be used by the receipt verification /
        lookup functionality.
        """

        statement = (
            select(
                Receipt,
            )
            .where(
                Receipt.verification_token
                == verification_token,
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Payment Transaction
    # ==========================================================

    async def get_by_payment_transaction_id(
        self,
        payment_transaction_id: int,
    ) -> Receipt | None:
        """
        Retrieve the receipt associated with a payment
        transaction.

        The database enforces the one-to-one relationship between
        PaymentTransaction and Receipt.
        """

        statement = (
            select(
                Receipt,
            )
            .where(
                Receipt.payment_transaction_id
                == payment_transaction_id,
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Customer Queries
    # ==========================================================

    async def get_customer_receipts(
        self,
        customer_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Receipt]:
        """
        Retrieve receipt history for a customer.

        Results are ordered from newest to oldest.
        """

        statement = (
            select(
                Receipt,
            )
            .where(
                Receipt.customer_id == customer_id,
            )
            .order_by(
                Receipt.created_at.desc(),
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
    # Status Queries
    # ==========================================================

    async def get_by_status(
        self,
        status: ReceiptStatus,
    ) -> list[Receipt]:
        """
        Retrieve receipts by status.
        """

        statement = (
            select(
                Receipt,
            )
            .where(
                Receipt.status == status,
            )
            .order_by(
                Receipt.created_at.desc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return list(
            result.scalars().all(),
        )

    # ==========================================================
    # Generation / Processing Queries
    # ==========================================================

    async def get_pending_receipts(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Receipt]:
        """
        Retrieve receipts that are pending generation.
        """

        statement = (
            select(
                Receipt,
            )
            .where(
                Receipt.status == ReceiptStatus.PENDING,
            )
            .order_by(
                Receipt.created_at.asc(),
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

    async def get_failed_receipts(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Receipt]:
        """
        Retrieve receipts whose generation failed.
        """

        statement = (
            select(
                Receipt,
            )
            .where(
                Receipt.status == ReceiptStatus.FAILED,
            )
            .order_by(
                Receipt.created_at.asc(),
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
    # Counts
    # ==========================================================

    async def count_all(
        self,
    ) -> int:
        """
        Count all receipts.
        """

        statement = (
            select(
                func.count(
                    Receipt.id,
                )
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one()

    async def count_by_status(
        self,
        status: ReceiptStatus,
    ) -> int:
        """
        Count receipts by status.
        """

        statement = (
            select(
                func.count(
                    Receipt.id,
                )
            )
            .where(
                Receipt.status == status,
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one()

    async def count_customer_receipts(
        self,
        customer_id: int,
    ) -> int:
        """
        Count receipts belonging to a customer.
        """

        statement = (
            select(
                func.count(
                    Receipt.id,
                )
            )
            .where(
                Receipt.customer_id == customer_id,
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one()