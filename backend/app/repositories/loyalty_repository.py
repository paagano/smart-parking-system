"""
Loyalty Repository.

Persistence layer for LoyaltyAccount and
LoyaltyPointTransaction entities.

Repositories contain ONLY database access logic.

Business rules belong in LoyaltyService.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    LoyaltyPointTransactionType,
)
from app.models.loyalty_account import (
    LoyaltyAccount,
)
from app.models.loyalty_point_transaction import (
    LoyaltyPointTransaction,
)
from app.repositories.base_repository import (
    BaseRepository,
)


class LoyaltyRepository(
    BaseRepository[LoyaltyAccount],
):
    """
    Repository responsible for LoyaltyAccount persistence
    and LoyaltyPointTransaction queries.
    """

    def __init__(
        self,
        db: AsyncSession,
    ) -> None:
        super().__init__(
            db=db,
            model=LoyaltyAccount,
        )

    # ==========================================================
    # Loyalty Account
    # ==========================================================

    async def get_by_id(
        self,
        loyalty_account_id: int,
    ) -> LoyaltyAccount | None:
        """
        Retrieve a loyalty account by its primary key.
        """

        return await super().get_by_id(
            loyalty_account_id,
        )

    async def get_by_customer_id(
        self,
        customer_id: int,
    ) -> LoyaltyAccount | None:
        """
        Retrieve a loyalty account using the customer ID.
        """

        result = await self.db.execute(
            select(
                LoyaltyAccount,
            ).where(
                LoyaltyAccount.customer_id == customer_id,
            )
        )

        return result.scalar_one_or_none()

    async def exists_for_customer(
        self,
        customer_id: int,
    ) -> bool:
        """
        Determine whether a loyalty account exists
        for the supplied customer.
        """

        account = await self.get_by_customer_id(
            customer_id,
        )

        return account is not None

    async def get_active_by_customer_id(
        self,
        customer_id: int,
    ) -> LoyaltyAccount | None:
        """
        Retrieve an active loyalty account for a customer.
        """

        result = await self.db.execute(
            select(
                LoyaltyAccount,
            ).where(
                LoyaltyAccount.customer_id == customer_id,
                LoyaltyAccount.is_active.is_(True),
            )
        )

        return result.scalar_one_or_none()

    async def get_all_active(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyAccount]:
        """
        Retrieve active loyalty accounts.

        Results are ordered from newest to oldest.
        """

        result = await self.db.execute(
            select(
                LoyaltyAccount,
            )
            .where(
                LoyaltyAccount.is_active.is_(True),
            )
            .order_by(
                LoyaltyAccount.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        return list(
            result.scalars().all(),
        )

    # ==========================================================
    # Point Transactions
    # ==========================================================

    async def get_point_transaction_by_id(
        self,
        transaction_id: int,
    ) -> LoyaltyPointTransaction | None:
        """
        Retrieve a loyalty point transaction by ID.
        """

        result = await self.db.execute(
            select(
                LoyaltyPointTransaction,
            ).where(
                LoyaltyPointTransaction.id == transaction_id,
            )
        )

        return result.scalar_one_or_none()

    async def get_point_transactions(
        self,
        loyalty_account_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyPointTransaction]:
        """
        Retrieve point transaction history for a loyalty account.

        Results are ordered from newest to oldest.
        """

        result = await self.db.execute(
            select(
                LoyaltyPointTransaction,
            )
            .where(
                LoyaltyPointTransaction.loyalty_account_id
                == loyalty_account_id,
            )
            .order_by(
                LoyaltyPointTransaction.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        return list(
            result.scalars().all(),
        )

    async def get_point_transactions_by_type(
        self,
        loyalty_account_id: int,
        transaction_type: LoyaltyPointTransactionType,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyPointTransaction]:
        """
        Retrieve point transactions of a specific type
        for a loyalty account.
        """

        result = await self.db.execute(
            select(
                LoyaltyPointTransaction,
            )
            .where(
                LoyaltyPointTransaction.loyalty_account_id
                == loyalty_account_id,
                LoyaltyPointTransaction.transaction_type
                == transaction_type,
            )
            .order_by(
                LoyaltyPointTransaction.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        return list(
            result.scalars().all(),
        )

    async def get_latest_point_transaction(
        self,
        loyalty_account_id: int,
    ) -> LoyaltyPointTransaction | None:
        """
        Retrieve the most recent point transaction
        for a loyalty account.

        When multiple transactions have the same created_at
        timestamp, the transaction with the highest ID is treated
        as the latest transaction.
        """

        result = await self.db.execute(
            select(
                LoyaltyPointTransaction,
            )
            .where(
                LoyaltyPointTransaction.loyalty_account_id
                == loyalty_account_id,
            )
            .order_by(
                LoyaltyPointTransaction.created_at.desc(),
                LoyaltyPointTransaction.id.desc(),
            )
            .limit(1)
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Reference Lookup
    # ==========================================================

    async def get_by_reference(
        self,
        reference_type: str,
        reference_id: int,
    ) -> list[LoyaltyPointTransaction]:
        """
        Retrieve point transactions associated with a
        specific business entity.

        Example:

            reference_type = "PAYMENT_TRANSACTION"
            reference_id = 101
        """

        result = await self.db.execute(
            select(
                LoyaltyPointTransaction,
            )
            .where(
                LoyaltyPointTransaction.reference_type
                == reference_type,
                LoyaltyPointTransaction.reference_id
                == reference_id,
            )
            .order_by(
                LoyaltyPointTransaction.created_at.desc(),
            )
        )

        return list(
            result.scalars().all(),
        )

    # ==========================================================
    # Counts
    # ==========================================================

    async def count_point_transactions(
        self,
        loyalty_account_id: int,
    ) -> int:
        """
        Count point transactions belonging to a loyalty account.
        """

        result = await self.db.execute(
            select(
                func.count(
                    LoyaltyPointTransaction.id,
                )
            ).where(
                LoyaltyPointTransaction.loyalty_account_id
                == loyalty_account_id,
            )
        )

        return result.scalar_one()