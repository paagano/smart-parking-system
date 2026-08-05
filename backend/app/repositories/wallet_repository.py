"""
Wallet Repository.

Persistence layer for Wallet entities.

Repositories contain ONLY database access logic.

Business rules belong in WalletService.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wallet import Wallet
from app.repositories.base_repository import BaseRepository


class WalletRepository(
    BaseRepository[Wallet],
):
    """
    Repository for Wallet persistence.
    """

    def __init__(
        self,
        db: AsyncSession,
    ) -> None:
        super().__init__(
            db=db,
            model=Wallet,
        )

    # ==========================================================
    # Read Operations
    # ==========================================================

    async def get_by_customer_id(
        self,
        customer_id: int,
    ) -> Wallet | None:
        """
        Retrieve a customer's wallet.

        Parameters
        ----------
        customer_id:
            Customer identifier.

        Returns
        -------
        Wallet | None
            Wallet if found; otherwise None.
        """

        result = await self.db.execute(
            select(Wallet).where(
                Wallet.customer_id == customer_id,
            )
        )

        return result.scalar_one_or_none()

    async def get_by_wallet_number(
        self,
        wallet_number: str,
    ) -> Wallet | None:
        """
        Retrieve a wallet by its wallet number.
        """

        result = await self.db.execute(
            select(Wallet).where(
                Wallet.wallet_number == wallet_number,
            )
        )

        return result.scalar_one_or_none()

    async def exists(
        self,
        customer_id: int,
    ) -> bool:
        """
        Determine whether a customer already owns a wallet.
        """

        wallet = await self.get_by_customer_id(
            customer_id,
        )

        return wallet is not None

        # ==========================================================
    # Concurrency Control
    # ==========================================================

    async def lock_wallet(
        self,
        wallet_id: int,
    ) -> Wallet | None:
        """
        Retrieve a wallet and acquire a row-level lock.

        This method uses PostgreSQL's SELECT ... FOR UPDATE
        to prevent concurrent transactions from modifying the
        same wallet simultaneously.

        Notes
        -----
        - The lock is released automatically when the current
          database transaction commits or rolls back.
        - This method should only be used inside a service
          method that performs financial operations.
        """

        result = await self.db.execute(
            select(Wallet)
            .where(
                Wallet.id == wallet_id,
            )
            .with_for_update()
        )

        return result.scalar_one_or_none()

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