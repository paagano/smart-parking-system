"""
Wallet Transaction Repository.

Persistence layer for WalletTransaction entities.

Repositories contain ONLY database access logic.

Business rules belong in WalletService.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WalletTransactionType
from app.models.wallet_transaction import WalletTransaction
from app.repositories.base_repository import BaseRepository


class WalletTransactionRepository(
    BaseRepository[WalletTransaction],
):
    """
    Repository responsible for WalletTransaction persistence.
    """

    def __init__(
        self,
        db: AsyncSession,
    ) -> None:
        super().__init__(
            db=db,
            model=WalletTransaction,
        )

    # ==========================================================
    # Lookup Operations
    # ==========================================================

    async def get_by_transaction_number(
        self,
        transaction_number: str,
    ) -> WalletTransaction | None:
        """
        Retrieve a WalletTransaction using its unique transaction number.
        """
        result = await self.db.execute(
            select(WalletTransaction).where(
                WalletTransaction.transaction_number == transaction_number,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_payment_transaction(
        self,
        payment_transaction_id: int,
    ) -> list[WalletTransaction]:
        """
        Retrieve every wallet transaction linked to a PaymentTransaction.
        """
        result = await self.db.execute(
            select(WalletTransaction)
            .where(
                WalletTransaction.payment_transaction_id == payment_transaction_id,
            )
            .order_by(
                desc(WalletTransaction.posted_at),
            )
        )
        return list(result.scalars().all())

    async def exists(
        self,
        transaction_number: str,
    ) -> bool:
        """
        Determine whether a wallet transaction already exists.
        """
        transaction = await self.get_by_transaction_number(transaction_number)
        return transaction is not None

    # ==========================================================
    # Wallet Queries
    # ==========================================================

    async def get_by_wallet(
        self,
        wallet_id: int,
    ) -> list[WalletTransaction]:
        """
        Retrieve every transaction belonging to a wallet.

        Transactions are returned newest first based on posting date.
        """
        result = await self.db.execute(
            select(WalletTransaction)
            .where(
                WalletTransaction.wallet_id == wallet_id,
            )
            .order_by(
                desc(WalletTransaction.posted_at),
            )
        )
        return list(result.scalars().all())

    async def get_latest(
        self,
        wallet_id: int,
        *,
        limit: int = 10,
    ) -> list[WalletTransaction]:
        """
        Retrieve the most recent wallet transactions.
        """
        result = await self.db.execute(
            select(WalletTransaction)
            .where(
                WalletTransaction.wallet_id == wallet_id,
            )
            .order_by(
                desc(WalletTransaction.posted_at),
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_last_transaction(
        self,
        wallet_id: int,
    ) -> WalletTransaction | None:
        """
        Retrieve the most recently posted wallet transaction.

        Returns
        -------
        WalletTransaction | None
        """
        result = await self.db.execute(
            select(WalletTransaction)
            .where(
                WalletTransaction.wallet_id == wallet_id,
            )
            .order_by(
                desc(WalletTransaction.posted_at),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_statement(
        self,
        wallet_id: int,
        *,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[WalletTransaction]:
        """
        Retrieve a wallet statement.

        If no dates are supplied, the complete wallet statement is returned.
        """
        query = select(WalletTransaction).where(
            WalletTransaction.wallet_id == wallet_id,
        )

        if from_date is not None:
            query = query.where(WalletTransaction.posted_at >= from_date)

        if to_date is not None:
            query = query.where(WalletTransaction.posted_at <= to_date)

        query = query.order_by(desc(WalletTransaction.posted_at))

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ==========================================================
    # Reporting Queries
    # ==========================================================

    async def get_credits(
        self,
        wallet_id: int,
    ) -> list[WalletTransaction]:
        """
        Retrieve all credit transactions for a wallet.

        Credits represent funds entering the wallet.
        """
        credit_types = [
            WalletTransactionType.TOP_UP,
            WalletTransactionType.OPENING_BALANCE,
            WalletTransactionType.CREDIT,
            WalletTransactionType.REFUND,
            WalletTransactionType.LOYALTY_REWARD,
        ]

        result = await self.db.execute(
            select(WalletTransaction)
            .where(
                and_(
                    WalletTransaction.wallet_id == wallet_id,
                    WalletTransaction.transaction_type.in_(credit_types),
                )
            )
            .order_by(
                desc(WalletTransaction.posted_at),
            )
        )
        return list(result.scalars().all())

    async def get_debits(
        self,
        wallet_id: int,
    ) -> list[WalletTransaction]:
        """
        Retrieve all debit transactions for a wallet.

        Debits represent funds leaving or being reserved from the wallet.
        """
        debit_types = [
            WalletTransactionType.DEBIT,
            WalletTransactionType.PAYMENT,
            WalletTransactionType.RESERVATION_HOLD,
            WalletTransactionType.LOYALTY_REDEMPTION,
        ]

        result = await self.db.execute(
            select(WalletTransaction)
            .where(
                and_(
                    WalletTransaction.wallet_id == wallet_id,
                    WalletTransaction.transaction_type.in_(debit_types),
                )
            )
            .order_by(
                desc(WalletTransaction.posted_at),
            )
        )
        return list(result.scalars().all())

    async def get_between_dates(
        self,
        wallet_id: int,
        from_date: datetime,
        to_date: datetime,
    ) -> list[WalletTransaction]:
        """
        Retrieve wallet transactions posted within the supplied date range.
        """
        result = await self.db.execute(
            select(WalletTransaction)
            .where(
                and_(
                    WalletTransaction.wallet_id == wallet_id,
                    WalletTransaction.posted_at >= from_date,
                    WalletTransaction.posted_at <= to_date,
                )
            )
            .order_by(
                desc(WalletTransaction.posted_at),
            )
        )
        return list(result.scalars().all())

    async def get_recent_transactions(
        self,
        *,
        limit: int = 25,
    ) -> list[WalletTransaction]:
        """
        Retrieve the most recently posted wallet transactions across the system.

        Intended for administration dashboards.
        """
        result = await self.db.execute(
            select(WalletTransaction)
            .order_by(
                desc(WalletTransaction.posted_at),
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    # ==========================================================
    # Statistics
    # ==========================================================

    async def count_transactions(
        self,
        wallet_id: int,
    ) -> int:
        """
        Return the total number of transactions belonging to a wallet.
        """
        result = await self.db.execute(
            select(func.count(WalletTransaction.id)).where(
                WalletTransaction.wallet_id == wallet_id,
            )
        )
        return result.scalar_one()

    async def sum_credits(
        self,
        wallet_id: int,
    ) -> Decimal:
        """
        Calculate the total amount credited to a wallet.

        The calculation is performed entirely by PostgreSQL.
        """
        credit_types = [
            WalletTransactionType.TOP_UP,
            WalletTransactionType.OPENING_BALANCE,
            WalletTransactionType.CREDIT,
            WalletTransactionType.REFUND,
            WalletTransactionType.LOYALTY_REWARD,
        ]

        result = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(WalletTransaction.amount),
                    Decimal("0.00"),
                )
            ).where(
                and_(
                    WalletTransaction.wallet_id == wallet_id,
                    WalletTransaction.transaction_type.in_(credit_types),
                )
            )
        )
        return result.scalar_one()

    async def sum_debits(
        self,
        wallet_id: int,
    ) -> Decimal:
        """
        Calculate the total amount debited from a wallet.

        The calculation is performed entirely by PostgreSQL.
        """
        debit_types = [
            WalletTransactionType.DEBIT,
            WalletTransactionType.PAYMENT,
            WalletTransactionType.RESERVATION_HOLD,
            WalletTransactionType.LOYALTY_REDEMPTION,
        ]

        result = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(WalletTransaction.amount),
                    Decimal("0.00"),
                )
            ).where(
                and_(
                    WalletTransaction.wallet_id == wallet_id,
                    WalletTransaction.transaction_type.in_(debit_types),
                )
            )
        )
        return result.scalar_one()

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(
        self,
    ) -> str:
        return (
            f"{self.__class__.__name__}"
            f"(model={self.model.__name__})"
        )