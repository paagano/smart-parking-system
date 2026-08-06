"""
Wallet Service.

Production-grade business service responsible for all wallet operations.

Responsibilities
----------------
- Wallet lifecycle management
- Balance management
- Immutable wallet ledger creation
- Fund reservation and release
- Wallet top-ups
- Wallet debits
- Refunds
- Reversals
- Wallet statements
- Integration with PaymentService

The WalletService owns all wallet-related business rules.
Repositories perform persistence only.

All financial operations are executed inside database
transactions to guarantee consistency.
"""

from __future__ import annotations

import logging

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    Currency,
    WalletStatus,
    WalletTransactionStatus,
    WalletTransactionType,
)

from app.models.wallet import Wallet
from app.models.wallet_transaction import WalletTransaction

from app.repositories.wallet_repository import WalletRepository
from app.repositories.wallet_transaction_repository import (
    WalletTransactionRepository,
)

from app.schemas.wallet import (
    WalletBalanceResponse,
)

logger = logging.getLogger(__name__)


class WalletService:
    """
    Production Wallet Service.

    Owns all wallet business logic.

    Responsibilities
    ----------------
    • Wallet creation
    • Balance updates
    • Ledger creation
    • Statement generation
    • Reservation handling
    • Refund processing
    • Reversals
    • Validation
    """

    def __init__(
        self,
        *,
        db: AsyncSession,
        wallet_repository: WalletRepository,
        wallet_transaction_repository: WalletTransactionRepository,
    ) -> None:

        self.db = db

        self.wallet_repository = wallet_repository

        self.wallet_transaction_repository = (
            wallet_transaction_repository
        )

    # ==========================================================
    # Private Helpers
    # ==========================================================

    @staticmethod
    def _generate_wallet_number() -> str:
        """
        Generate a unique wallet number.

        Example
        -------
        WAL-4F8C92A1
        """

        return (
            "WAL-"
            f"{uuid4().hex[:8].upper()}"
        )

    @staticmethod
    def _generate_transaction_number() -> str:
        """
        Generate a unique wallet transaction number.

        Example
        -------
        WTX-82C6F97A1A2B
        """

        return (
            "WTX-"
            f"{uuid4().hex[:12].upper()}"
        )

    @staticmethod
    def _utcnow() -> datetime:
        """
        Return a timezone-aware UTC timestamp.
        """

        return datetime.now(
            timezone.utc,
        )

        # ==========================================================
    # Validation Helpers
    # ==========================================================

    @staticmethod
    def _validate_amount(
        amount: Decimal,
    ) -> None:
        """
        Validate a monetary amount.
        """

        if amount <= Decimal("0.00"):
            raise ValueError(
                "Amount must be greater than zero."
            )

    @staticmethod
    def _validate_wallet(
        wallet: Wallet,
    ) -> None:
        """
        Ensure the wallet can participate in
        financial transactions.
        """

        if wallet.status != WalletStatus.ACTIVE:
            raise ValueError(
                f"Wallet is {wallet.status.value}."
            )

    @staticmethod
    def _ensure_sufficient_balance(
        wallet: Wallet,
        amount: Decimal,
    ) -> None:
        """
        Ensure the wallet has enough available
        balance.
        """

        if wallet.available_balance < amount:
            raise ValueError(
                "Insufficient wallet balance."
            )

    @staticmethod
    def _ensure_sufficient_reserved_balance(
        wallet: Wallet,
        amount: Decimal,
    ) -> None:
        """
        Ensure sufficient reserved funds exist.
        """

        if wallet.reserved_balance < amount:
            raise ValueError(
                "Insufficient reserved balance."
            )

    # ==========================================================
    # Wallet Retrieval
    # ==========================================================

    async def get_wallet(
        self,
        wallet_id: int,
    ) -> Wallet:
        """
        Retrieve a wallet by its primary key.

        Raises
        ------
        ValueError
            If the wallet does not exist.
        """

        wallet = await self.wallet_repository.get_by_id(
            wallet_id,
        )

        if wallet is None:
            raise ValueError(
                "Wallet not found."
            )

        return wallet

    async def get_wallet_by_customer(
        self,
        customer_id: int,
    ) -> Wallet:
        """
        Retrieve a customer's wallet.
        """

        wallet = (
            await self.wallet_repository.get_by_customer_id(
                customer_id,
            )
        )

        if wallet is None:
            raise ValueError(
                "Wallet not found."
            )

        return wallet

    async def get_wallet_by_number(
        self,
        wallet_number: str,
    ) -> Wallet:
        """
        Retrieve a wallet using its wallet number.
        """

        wallet = (
            await self.wallet_repository.get_by_wallet_number(
                wallet_number,
            )
        )

        if wallet is None:
            raise ValueError(
                "Wallet not found."
            )

        return wallet

    async def get_wallet_for_update(
        self,
        wallet_id: int,
    ) -> Wallet:
        """
        Retrieve and lock a wallet for update.

        Used by every financial operation to
        prevent concurrent balance modifications.
        """

        wallet = (
            await self.wallet_repository.lock_wallet(
                wallet_id,
            )
        )

        if wallet is None:
            raise ValueError(
                "Wallet not found."
            )

        self._validate_wallet(
            wallet,
        )

        return wallet

    async def get_balance(
        self,
        wallet_id: int,
    ) -> Decimal:
        """
        Retrieve the wallet's available balance.
        """

        wallet = await self.get_wallet(
            wallet_id,
        )

        return wallet.available_balance

    async def get_reserved_balance(
        self,
        wallet_id: int,
    ) -> Decimal:
        """
        Retrieve the wallet's reserved balance.
        """

        wallet = await self.get_wallet(
            wallet_id,
        )

        return wallet.reserved_balance

    async def get_total_balance(
        self,
        wallet_id: int,
    ) -> Decimal:
        """
        Retrieve the wallet's total balance.

        Available + Reserved.
        """

        wallet = await self.get_wallet(
            wallet_id,
        )

        return (
            wallet.available_balance
            + wallet.reserved_balance
        )

        # ==========================================================
    # Ledger Helpers
    # ==========================================================

    async def _create_wallet_transaction(
        self,
        *,
        wallet: Wallet,
        transaction_type: WalletTransactionType,
        amount: Decimal,
        balance_before: Decimal,
        balance_after: Decimal,
        payment_transaction_id: int | None = None,
        created_by: int | None = None,
        reference: str | None = None,
        description: str | None = None,
        notes: str | None = None,
        status: WalletTransactionStatus = (
            WalletTransactionStatus.COMPLETED
        ),
        currency: Currency | None = None,
    ) -> WalletTransaction:
        """
        Create a wallet ledger entry.

        This method ONLY creates the immutable ledger
        record.

        It does NOT modify wallet balances.

        Balance mutations are performed by the caller.
        """

        transaction = WalletTransaction(

            wallet_id=wallet.id,

            payment_transaction_id=payment_transaction_id,

            created_by=created_by,

            transaction_number=(
                self._generate_transaction_number()
            ),

            reference=reference,

            transaction_type=transaction_type,

            status=status,

            currency=(
                currency
                if currency is not None
                else wallet.currency
            ),

            amount=amount,

            balance_before=balance_before,

            balance_after=balance_after,

            description=description,

            notes=notes,

            posted_at=self._utcnow(),
        )

        return await (
            self.wallet_transaction_repository.save(
                transaction,
            )
        )

    async def _update_wallet_audit(
        self,
        wallet: Wallet,
    ) -> None:
        """
        Update wallet audit fields.
        """

        wallet.last_transaction_at = (
            self._utcnow()
        )

        await self.wallet_repository.save(
            wallet,
        )

    async def _persist_wallet_changes(
        self,
        wallet: Wallet,
    ) -> Wallet:
        """
        Persist wallet changes.

        Commit is intentionally NOT performed here.

        Transaction management belongs to the public
        service methods.
        """

        await self.wallet_repository.save(
            wallet,
        )

        return wallet

    async def _commit(
        self,
    ) -> None:
        """
        Commit the current transaction.
        """

        await self.wallet_repository.commit()

    async def _rollback(
        self,
    ) -> None:
        """
        Roll back the current transaction.
        """

        await self.wallet_repository.rollback()

    async def _refresh_wallet(
        self,
        wallet: Wallet,
    ) -> Wallet:
        """
        Refresh the wallet from the database.
        """

        return await self.wallet_repository.refresh(
            wallet,
        )

    async def _record_transaction(
        self,
        *,
        wallet: Wallet,
        transaction_type: WalletTransactionType,
        amount: Decimal,
        balance_before: Decimal,
        balance_after: Decimal,
        payment_transaction_id: int | None = None,
        created_by: int | None = None,
        reference: str | None = None,
        description: str | None = None,
        notes: str | None = None,
    ) -> WalletTransaction:
        """
        Convenience wrapper around
        _create_wallet_transaction().

        Keeps all ledger creation centralized.
        """

        return await self._create_wallet_transaction(
            wallet=wallet,
            transaction_type=transaction_type,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            payment_transaction_id=payment_transaction_id,
            created_by=created_by,
            reference=reference,
            description=description,
            notes=notes,
        )

    # ==========================================================
    # Wallet Creation
    # ==========================================================

    async def create_wallet(
        self,
        *,
        customer_id: int,
        currency: Currency = Currency.KES,
    ) -> Wallet:
        """
        Create a wallet for a customer.

        A customer may own only one wallet.
        """

        existing_wallet = (
            await self.wallet_repository.get_by_customer_id(
                customer_id,
            )
        )

        if existing_wallet is not None:
            raise ValueError(
                "Customer already owns a wallet."
            )

        wallet = Wallet(
            wallet_number=self._generate_wallet_number(),
            customer_id=customer_id,
            currency=currency,
            status=WalletStatus.ACTIVE,
            available_balance=Decimal("0.00"),
            reserved_balance=Decimal("0.00"),
            total_credited=Decimal("0.00"),
            total_debited=Decimal("0.00"),
        )

        try:

            await self.wallet_repository.save(
                wallet,
            )

            await self.wallet_repository.commit()

            await self.wallet_repository.refresh(
                wallet,
            )

            logger.info(
                "Wallet %s created for customer %s.",
                wallet.wallet_number,
                customer_id,
            )

            return wallet

        except Exception:

            await self.wallet_repository.rollback()

            logger.exception(
                "Failed to create wallet."
            )

            raise

    # ==========================================================
    # Credit Operations
    # ==========================================================

    async def credit_wallet(
        self,
        *,
        wallet_id: int,
        amount: Decimal,
        transaction_type: WalletTransactionType = (
            WalletTransactionType.TOP_UP
        ),
        payment_transaction_id: int | None = None,
        created_by: int | None = None,
        reference: str | None = None,
        description: str | None = None,
        notes: str | None = None,
    ) -> Wallet:
        """
        Credit funds into a wallet.
        """

        self._validate_amount(
            amount,
        )

        wallet = await self.get_wallet_for_update(
            wallet_id,
        )

        balance_before = wallet.available_balance

        wallet.available_balance += amount

        wallet.total_credited += amount

        balance_after = wallet.available_balance

        try:

            await self._persist_wallet_changes(
                wallet,
            )

            await self._record_transaction(
                wallet=wallet,
                transaction_type=transaction_type,
                amount=amount,
                balance_before=balance_before,
                balance_after=balance_after,
                payment_transaction_id=payment_transaction_id,
                created_by=created_by,
                reference=reference,
                description=description,
                notes=notes,
            )

            await self._update_wallet_audit(
                wallet,
            )

            await self._commit()

            await self._refresh_wallet(
                wallet,
            )

            logger.info(
                "Wallet %s credited by %s.",
                wallet.wallet_number,
                amount,
            )

            return wallet

        except Exception:

            await self._rollback()

            logger.exception(
                "Wallet credit failed."
            )

            raise

    # ==========================================================
    # Debit Operations
    # ==========================================================

    async def debit_wallet(
        self,
        *,
        wallet_id: int,
        amount: Decimal,
        payment_transaction_id: int | None = None,
        created_by: int | None = None,
        reference: str | None = None,
        description: str | None = None,
        notes: str | None = None,
    ) -> Wallet:
        """
        Debit funds from a wallet.
        """

        self._validate_amount(
            amount,
        )

        wallet = await self.get_wallet_for_update(
            wallet_id,
        )

        self._ensure_sufficient_balance(
            wallet,
            amount,
        )

        balance_before = wallet.available_balance

        wallet.available_balance -= amount

        wallet.total_debited += amount

        balance_after = wallet.available_balance

        try:

            await self._persist_wallet_changes(
                wallet,
            )

            await self._record_transaction(
                wallet=wallet,
                transaction_type=WalletTransactionType.DEBIT,
                amount=amount,
                balance_before=balance_before,
                balance_after=balance_after,
                payment_transaction_id=payment_transaction_id,
                created_by=created_by,
                reference=reference,
                description=description,
                notes=notes,
            )

            await self._update_wallet_audit(
                wallet,
            )

            await self._commit()

            await self._refresh_wallet(
                wallet,
            )

            logger.info(
                "Wallet %s debited by %s.",
                wallet.wallet_number,
                amount,
            )

            return wallet

        except Exception:

            await self._rollback()

            logger.exception(
                "Wallet debit failed."
            )

            raise

        # ==========================================================
    # Reservation Operations
    # ==========================================================

    async def reserve_funds(
        self,
        *,
        wallet_id: int,
        amount: Decimal,
        created_by: int | None = None,
        reference: str | None = None,
        description: str | None = None,
        notes: str | None = None,
    ) -> Wallet:
        """
        Reserve funds within a wallet.

        Reserved funds remain unavailable until they
        are either released or converted into a payment.
        """

        self._validate_amount(amount)

        wallet = await self.get_wallet_for_update(
            wallet_id,
        )

        self._ensure_sufficient_balance(
            wallet,
            amount,
        )

        balance_before = wallet.available_balance

        wallet.available_balance -= amount
        wallet.reserved_balance += amount

        balance_after = wallet.available_balance

        try:

            await self._persist_wallet_changes(
                wallet,
            )

            await self._record_transaction(
                wallet=wallet,
                transaction_type=(
                    WalletTransactionType.RESERVATION_HOLD
                ),
                amount=amount,
                balance_before=balance_before,
                balance_after=balance_after,
                created_by=created_by,
                reference=reference,
                description=description,
                notes=notes,
            )

            await self._update_wallet_audit(
                wallet,
            )

            await self._commit()

            return await self._refresh_wallet(
                wallet,
            )

        except Exception:

            await self._rollback()
            logger.exception(
                "Failed to reserve wallet funds."
            )
            raise

    async def release_reserved_funds(
        self,
        *,
        wallet_id: int,
        amount: Decimal,
        created_by: int | None = None,
        reference: str | None = None,
        description: str | None = None,
        notes: str | None = None,
    ) -> Wallet:
        """
        Release previously reserved funds.
        """

        self._validate_amount(
            amount,
        )

        wallet = await self.get_wallet_for_update(
            wallet_id,
        )

        self._ensure_sufficient_reserved_balance(
            wallet,
            amount,
        )

        balance_before = wallet.available_balance

        wallet.reserved_balance -= amount
        wallet.available_balance += amount

        balance_after = wallet.available_balance

        try:

            await self._persist_wallet_changes(
                wallet,
            )

            await self._record_transaction(
                wallet=wallet,
                transaction_type=(
                    WalletTransactionType.RESERVATION_RELEASE
                ),
                amount=amount,
                balance_before=balance_before,
                balance_after=balance_after,
                created_by=created_by,
                reference=reference,
                description=description,
                notes=notes,
            )

            await self._update_wallet_audit(
                wallet,
            )

            await self._commit()

            return await self._refresh_wallet(
                wallet,
            )

        except Exception:

            await self._rollback()

            logger.exception(
                "Failed to release reserved funds."
            )

            raise

    # ==========================================================
    # Refund Operations
    # ==========================================================

    async def refund_wallet(
        self,
        *,
        wallet_id: int,
        amount: Decimal,
        payment_transaction_id: int | None = None,
        created_by: int | None = None,
        reference: str | None = None,
        description: str | None = None,
        notes: str | None = None,
    ) -> Wallet:
        """
        Refund money back into a wallet.
        """

        return await self.credit_wallet(
            wallet_id=wallet_id,
            amount=amount,
            transaction_type=WalletTransactionType.REFUND,
            payment_transaction_id=payment_transaction_id,
            created_by=created_by,
            reference=reference,
            description=description,
            notes=notes,
        )

    # ==========================================================
    # Reversal Operations
    # ==========================================================

    async def reverse_transaction(
        self,
        *,
        wallet_id: int,
        amount: Decimal,
        payment_transaction_id: int | None = None,
        created_by: int | None = None,
        reference: str | None = None,
        description: str | None = None,
        notes: str | None = None,
    ) -> Wallet:
        """
        Reverse a previous wallet debit.

        This creates a new immutable ledger entry rather
        than modifying the original transaction.
        """

        return await self.credit_wallet(
            wallet_id=wallet_id,
            amount=amount,
            transaction_type=WalletTransactionType.REVERSAL,
            payment_transaction_id=payment_transaction_id,
            created_by=created_by,
            reference=reference,
            description=description,
            notes=notes,
        )

        # ==========================================================
    # Wallet Statements
    # ==========================================================

    async def get_statement(
        self,
        *,
        wallet_id: int,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[WalletTransaction]:
        """
        Retrieve a wallet statement.
        """

        await self.get_wallet(
            wallet_id,
        )

        return await (
            self.wallet_transaction_repository.get_statement(
                wallet_id=wallet_id,
                from_date=from_date,
                to_date=to_date,
            )
        )

    async def get_recent_transactions(
        self,
        *,
        wallet_id: int,
        limit: int = 10,
    ) -> list[WalletTransaction]:
        """
        Retrieve the most recent wallet transactions.
        """

        await self.get_wallet(
            wallet_id,
        )

        return await (
            self.wallet_transaction_repository.get_latest(
                wallet_id=wallet_id,
                limit=limit,
            )
        )

    async def get_transaction(
        self,
        transaction_number: str,
    ) -> WalletTransaction:
        """
        Retrieve a wallet transaction by its
        transaction number.
        """

        transaction = await (
            self.wallet_transaction_repository
            .get_by_transaction_number(
                transaction_number,
            )
        )

        if transaction is None:
            raise ValueError(
                "Wallet transaction not found."
            )

        return transaction

    # ==========================================================
    # Statistics
    # ==========================================================

    async def get_wallet_summary(
        self,
        wallet_id: int,
    ) -> dict:
        """
        Retrieve a wallet summary.

        Intended for dashboards and API responses.
        """

        wallet = await self.get_wallet(
            wallet_id,
        )

        total_transactions = (
            await self.wallet_transaction_repository
            .count_transactions(
                wallet_id,
            )
        )

        total_credits = (
            await self.wallet_transaction_repository
            .sum_credits(
                wallet_id,
            )
        )

        total_debits = (
            await self.wallet_transaction_repository
            .sum_debits(
                wallet_id,
            )
        )

        return {
            "wallet_id": wallet.id,
            "wallet_number": wallet.wallet_number,
            "customer_id": wallet.customer_id,
            "currency": wallet.currency,
            "status": wallet.status,
            "available_balance": wallet.available_balance,
            "reserved_balance": wallet.reserved_balance,
            "current_balance": wallet.current_balance,
            "total_credited": wallet.total_credited,
            "total_debited": wallet.total_debited,
            "ledger_total_credits": total_credits,
            "ledger_total_debits": total_debits,
            "transaction_count": total_transactions,
            "last_transaction_at": wallet.last_transaction_at,
        }

    async def get_system_recent_transactions(
        self,
        *,
        limit: int = 50,
    ) -> list[WalletTransaction]:
        """
        Retrieve the most recent wallet transactions
        across the entire platform.

        Intended for administration dashboards.
        """

        return await (
            self.wallet_transaction_repository
            .get_recent_transactions(
                limit=limit,
            )
        )

    # ==========================================================
    # Wallet Query Operations
    # ==========================================================

    async def get_customer_wallet(
        self,
        customer_id: int,
    ) -> Wallet:
        """
        Retrieve a customer's wallet.
        """

        return await self.get_wallet_by_customer(
            customer_id,
        )


    async def get_customer_wallet_balance(
        self,
        customer_id: int,
    ) -> WalletBalanceResponse:
        """
        Retrieve a customer's wallet balance.
        """

        wallet = await self.get_wallet_by_customer(
            customer_id,
        )

        return WalletBalanceResponse(

            wallet_id=wallet.id,

            wallet_number=wallet.wallet_number,

            currency=wallet.currency,

            available_balance=wallet.available_balance,

            reserved_balance=wallet.reserved_balance,

            current_balance=(
                wallet.available_balance
                + wallet.reserved_balance
            ),
        )

        return wallet.available_balance


    async def get_customer_wallet_transactions(
        self,
        customer_id: int,
    ) -> list[WalletTransaction]:
        """
        Retrieve every wallet transaction
        belonging to a customer.
        """

        wallet = await self.get_wallet_by_customer(
            customer_id,
        )

        return await (
            self.wallet_transaction_repository.get_by_wallet(
                wallet.id,
            )
        )

    # ==========================================================
    # Health / Utility
    # ==========================================================

    async def wallet_exists(
        self,
        wallet_id: int,
    ) -> bool:
        """
        Determine whether a wallet exists.
        """

        wallet = await (
            self.wallet_repository.get_by_id(
                wallet_id,
            )
        )

        return wallet is not None

    async def transaction_exists(
        self,
        transaction_number: str,
    ) -> bool:
        """
        Determine whether a wallet transaction exists.
        """

        return await (
            self.wallet_transaction_repository.exists(
                transaction_number,
            )
        )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(
        self,
    ) -> str:
        return (
            f"{self.__class__.__name__}("
            f"repository={self.wallet_repository.__class__.__name__}, "
            f"ledger_repository="
            f"{self.wallet_transaction_repository.__class__.__name__}"
            f")"
        )