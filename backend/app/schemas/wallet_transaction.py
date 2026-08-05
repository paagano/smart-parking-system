"""
Wallet Repository.

Persistence layer for Wallet entities.

Repositories contain ONLY database access logic.

Business rules belong in WalletService.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wallet import Wallet
from app.repositories.base_repository import BaseRepository


class WalletRepository(BaseRepository[Wallet]):
    """
    Repository responsible for Wallet persistence.
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
    # Lookup Operations
    # ==========================================================

    async def get_by_customer_id(
        self,
        customer_id: int,
    ) -> Wallet | None:
        """
        Retrieve a wallet by its customer ID.
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
        Retrieve a wallet by its unique wallet number.
        """
        result = await self.db.execute(
            select(Wallet).where(
                Wallet.wallet_number == wallet_number,
            )
        )
        return result.scalar_one_or_none()

    async def get_with_balance_above(
        self,
        minimum_balance: Decimal,
        *,
        limit: int = 100,
    ) -> list[Wallet]:
        """
        Retrieve wallets with balance above the specified minimum.
        """
        result = await self.db.execute(
            select(Wallet)
            .where(
                Wallet.balance >= minimum_balance,
            )
            .order_by(
                Wallet.balance.desc(),
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_with_balance_below(
        self,
        maximum_balance: Decimal,
        *,
        limit: int = 100,
    ) -> list[Wallet]:
        """
        Retrieve wallets with balance below the specified maximum.
        """
        result = await self.db.execute(
            select(Wallet)
            .where(
                Wallet.balance <= maximum_balance,
            )
            .order_by(
                Wallet.balance.asc(),
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_active_wallets(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Wallet]:
        """
        Retrieve all active wallets.
        """
        result = await self.db.execute(
            select(Wallet)
            .where(
                Wallet.is_active == True,
            )
            .order_by(
                Wallet.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_inactive_wallets(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Wallet]:
        """
        Retrieve all inactive wallets.
        """
        result = await self.db.execute(
            select(Wallet)
            .where(
                Wallet.is_active == False,
            )
            .order_by(
                Wallet.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    # ==========================================================
    # Balance Operations
    # ==========================================================

    async def get_balance(
        self,
        wallet_id: int,
    ) -> Decimal:
        """
        Retrieve the current balance of a wallet.
        """
        wallet = await self.get_by_id(wallet_id)
        if wallet is None:
            raise ValueError(f"Wallet with ID {wallet_id} not found.")
        return wallet.balance

    async def update_balance(
        self,
        wallet_id: int,
        new_balance: Decimal,
    ) -> Wallet:
        """
        Update the balance of a wallet.
        """
        wallet = await self.get_by_id(wallet_id)
        if wallet is None:
            raise ValueError(f"Wallet with ID {wallet_id} not found.")

        wallet.balance = new_balance
        wallet.updated_at = func.now()

        await self.db.flush()
        await self.db.refresh(wallet)

        return wallet

    async def add_balance(
        self,
        wallet_id: int,
        amount: Decimal,
    ) -> Wallet:
        """
        Add funds to a wallet balance.
        """
        if amount <= 0:
            raise ValueError("Amount must be greater than zero.")

        wallet = await self.get_by_id(wallet_id)
        if wallet is None:
            raise ValueError(f"Wallet with ID {wallet_id} not found.")

        wallet.balance += amount
        wallet.updated_at = func.now()

        await self.db.flush()
        await self.db.refresh(wallet)

        return wallet

    async def deduct_balance(
        self,
        wallet_id: int,
        amount: Decimal,
    ) -> Wallet:
        """
        Deduct funds from a wallet balance.
        """
        if amount <= 0:
            raise ValueError("Amount must be greater than zero.")

        wallet = await self.get_by_id(wallet_id)
        if wallet is None:
            raise ValueError(f"Wallet with ID {wallet_id} not found.")

        if wallet.balance < amount:
            raise ValueError(
                f"Insufficient balance. Available: {wallet.balance}, Required: {amount}"
            )

        wallet.balance -= amount
        wallet.updated_at = func.now()

        await self.db.flush()
        await self.db.refresh(wallet)

        return wallet

    async def reserve_balance(
        self,
        wallet_id: int,
        amount: Decimal,
    ) -> Wallet:
        """
        Reserve funds from a wallet balance.
        """
        if amount <= 0:
            raise ValueError("Amount must be greater than zero.")

        wallet = await self.get_by_id(wallet_id)
        if wallet is None:
            raise ValueError(f"Wallet with ID {wallet_id} not found.")

        available_balance = wallet.balance - wallet.reserved_balance
        if available_balance < amount:
            raise ValueError(
                f"Insufficient available balance. "
                f"Available: {available_balance}, Required: {amount}"
            )

        wallet.reserved_balance += amount
        wallet.updated_at = func.now()

        await self.db.flush()
        await self.db.refresh(wallet)

        return wallet

    async def release_reserved_balance(
        self,
        wallet_id: int,
        amount: Decimal,
    ) -> Wallet:
        """
        Release reserved funds from a wallet balance.
        """
        if amount <= 0:
            raise ValueError("Amount must be greater than zero.")

        wallet = await self.get_by_id(wallet_id)
        if wallet is None:
            raise ValueError(f"Wallet with ID {wallet_id} not found.")

        if wallet.reserved_balance < amount:
            raise ValueError(
                f"Insufficient reserved balance. "
                f"Reserved: {wallet.reserved_balance}, Requested: {amount}"
            )

        wallet.reserved_balance -= amount
        wallet.updated_at = func.now()

        await self.db.flush()
        await self.db.refresh(wallet)

        return wallet

    # ==========================================================
    # Status Operations
    # ==========================================================

    async def activate_wallet(
        self,
        wallet_id: int,
    ) -> Wallet:
        """
        Activate a wallet.
        """
        wallet = await self.get_by_id(wallet_id)
        if wallet is None:
            raise ValueError(f"Wallet with ID {wallet_id} not found.")

        wallet.is_active = True
        wallet.activated_at = func.now()
        wallet.updated_at = func.now()

        await self.db.flush()
        await self.db.refresh(wallet)

        return wallet

    async def deactivate_wallet(
        self,
        wallet_id: int,
        reason: str | None = None,
    ) -> Wallet:
        """
        Deactivate a wallet.
        """
        wallet = await self.get_by_id(wallet_id)
        if wallet is None:
            raise ValueError(f"Wallet with ID {wallet_id} not found.")

        if wallet.balance > 0:
            raise ValueError(
                f"Cannot deactivate wallet with positive balance: {wallet.balance}"
            )

        wallet.is_active = False
        wallet.deactivated_at = func.now()
        wallet.deactivation_reason = reason
        wallet.updated_at = func.now()

        await self.db.flush()
        await self.db.refresh(wallet)

        return wallet

    # ==========================================================
    # Statistics
    # ==========================================================

    async def count_active_wallets(self) -> int:
        """
        Count all active wallets.
        """
        result = await self.db.execute(
            select(func.count(Wallet.id)).where(
                Wallet.is_active == True,
            )
        )
        return result.scalar_one()

    async def count_inactive_wallets(self) -> int:
        """
        Count all inactive wallets.
        """
        result = await self.db.execute(
            select(func.count(Wallet.id)).where(
                Wallet.is_active == False,
            )
        )
        return result.scalar_one()

    async def total_balance_all_wallets(self) -> Decimal:
        """
        Calculate the total balance across all wallets.
        """
        result = await self.db.execute(
            select(func.coalesce(func.sum(Wallet.balance), Decimal("0.00")))
        )
        return result.scalar_one()

    async def total_reserved_balance_all_wallets(self) -> Decimal:
        """
        Calculate the total reserved balance across all wallets.
        """
        result = await self.db.execute(
            select(func.coalesce(func.sum(Wallet.reserved_balance), Decimal("0.00")))
        )
        return result.scalar_one()

    async def available_balance_all_wallets(self) -> Decimal:
        """
        Calculate the total available balance across all wallets.
        """
        result = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(Wallet.balance - Wallet.reserved_balance),
                    Decimal("0.00"),
                )
            )
        )
        return result.scalar_one()

    async def average_balance(self) -> Decimal:
        """
        Calculate the average balance across all wallets.
        """
        result = await self.db.execute(
            select(func.coalesce(func.avg(Wallet.balance), Decimal("0.00")))
        )
        return result.scalar_one()

    # ==========================================================
    # Existence Checks
    # ==========================================================

    async def wallet_exists_for_customer(
        self,
        customer_id: int,
    ) -> bool:
        """
        Check if a wallet exists for a customer.
        """
        wallet = await self.get_by_customer_id(customer_id)
        return wallet is not None

    async def wallet_exists(
        self,
        wallet_number: str,
    ) -> bool:
        """
        Check if a wallet exists by its number.
        """
        wallet = await self.get_by_wallet_number(wallet_number)
        return wallet is not None

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