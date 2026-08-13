"""
Loyalty Service.

Contains business logic for the SmartPark Loyalty Engine.

Responsibilities
----------------
- Loyalty account creation and retrieval
- Loyalty point awarding
- Loyalty point redemption
- Loyalty point adjustments
- Loyalty point reversal
- Loyalty point history
- Lifetime point tracking
- Loyalty tier evaluation

Persistence is delegated to LoyaltyRepository.

Business rules belong in this service.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.handlers import (
    BadRequestException,
    NotFoundException,
)

from app.models.enums import (
    LoyaltyPointTransactionType,
    LoyaltyTier,
)

from app.models.loyalty_account import (
    LoyaltyAccount,
)

from app.models.loyalty_point_transaction import (
    LoyaltyPointTransaction,
)

from app.repositories.loyalty_repository import (
    LoyaltyRepository,
)


class LoyaltyService:
    """
    Service responsible for SmartPark Loyalty business logic.
    """

    # ==========================================================
    # Loyalty Tier Thresholds
    # ==========================================================

    # These are the initial thresholds for the Loyalty Engine.
    #
    # They are deliberately kept in one place so they can be
    # changed later without modifying the rest of the service.
    #
    # Final commercial values can be agreed during hardening /
    # business configuration.

    SILVER_THRESHOLD = 1_000
    GOLD_THRESHOLD = 5_000
    PLATINUM_THRESHOLD = 10_000

    # ==========================================================
    # Construction
    # ==========================================================

    def __init__(
        self,
        db: AsyncSession,
        repository: LoyaltyRepository,
    ) -> None:
        """
        Create a LoyaltyService instance.
        """

        self.db = db
        self.repository = repository

    # ==========================================================
    # Loyalty Account
    # ==========================================================

    async def get_account(
        self,
        customer_id: int,
    ) -> LoyaltyAccount:
        """
        Retrieve a customer's loyalty account.

        Raises
        ------
        NotFoundException
            If the loyalty account does not exist.
        """

        account = await self.repository.get_by_customer_id(
            customer_id,
        )

        if account is None:
            raise NotFoundException(
                "Loyalty account not found.",
            )

        return account

    async def get_or_create_account(
        self,
        customer_id: int,
    ) -> LoyaltyAccount:
        """
        Retrieve an existing loyalty account or create one.

        A new loyalty account starts with:

        - 0 points
        - 0 lifetime points
        - BRONZE tier
        - active status
        """

        account = await self.repository.get_by_customer_id(
            customer_id,
        )

        if account is not None:
            return account

        account = LoyaltyAccount(
            customer_id=customer_id,
            points_balance=0,
            lifetime_points=0,
            tier=LoyaltyTier.BRONZE,
            is_active=True,
        )

        account = await self.repository.save(
            account,
        )

        await self.db.commit()

        await self.db.refresh(
            account,
        )

        return account

    # ==========================================================
    # Point Awarding
    # ==========================================================

    async def award_points(
        self,
        *,
        customer_id: int,
        points: int,
        transaction_type: LoyaltyPointTransactionType = (
            LoyaltyPointTransactionType.EARN
        ),
        reference_type: str | None = None,
        reference_id: int | None = None,
        description: str | None = None,
    ) -> LoyaltyPointTransaction:
        """
        Award loyalty points to a customer.

        Positive points are added to:

        - points_balance
        - lifetime_points

        A corresponding ledger transaction is created.

        If a reference is supplied and an identical transaction
        already exists for that reference, the existing transaction
        is returned. This provides basic idempotency for business
        events such as payment-based point awards.

        Raises
        ------
        BadRequestException
            If points are less than or equal to zero.

        NotFoundException
            If the loyalty account does not exist or is inactive.
        """

        if points <= 0:
            raise BadRequestException(
                "Points to award must be greater than zero.",
            )

        account = await self.repository.get_by_customer_id(
            customer_id,
        )

        if account is None:
            raise NotFoundException(
                "Loyalty account not found.",
            )

        if not account.is_active:
            raise BadRequestException(
                "Loyalty account is inactive.",
            )

        # ------------------------------------------------------
        # Basic Idempotency
        # ------------------------------------------------------

        if (
            reference_type is not None
            and reference_id is not None
        ):
            existing_transactions = (
                await self.repository.get_by_reference(
                    reference_type=reference_type,
                    reference_id=reference_id,
                )
            )

            for transaction in existing_transactions:
                if (
                    transaction.transaction_type
                    == transaction_type
                ):
                    return transaction

        # ------------------------------------------------------
        # Update Account
        # ------------------------------------------------------

        account.points_balance += points
        account.lifetime_points += points

        # ------------------------------------------------------
        # Evaluate Tier
        # ------------------------------------------------------

        account.tier = self._determine_tier(
            account.lifetime_points,
        )

        # ------------------------------------------------------
        # Create Ledger Transaction
        # ------------------------------------------------------

        transaction = LoyaltyPointTransaction(
            loyalty_account_id=account.id,
            transaction_type=transaction_type,
            points=points,
            balance_after=account.points_balance,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
        )

        await self.repository.save(
            transaction,
        )

        await self.db.commit()

        await self.db.refresh(
            transaction,
        )

        return transaction

    # ==========================================================
    # Point Redemption
    # ==========================================================

    async def redeem_points(
        self,
        *,
        customer_id: int,
        points: int,
        reference_type: str | None = None,
        reference_id: int | None = None,
        description: str | None = None,
    ) -> LoyaltyPointTransaction:
        """
        Redeem loyalty points from a customer's balance.

        Redemption decreases the customer's current balance but
        does NOT decrease lifetime_points.

        Raises
        ------
        BadRequestException
            If points are invalid, the account is inactive, or
            the customer has insufficient points.

        NotFoundException
            If the loyalty account does not exist.
        """

        if points <= 0:
            raise BadRequestException(
                "Points to redeem must be greater than zero.",
            )

        account = await self.repository.get_by_customer_id(
            customer_id,
        )

        if account is None:
            raise NotFoundException(
                "Loyalty account not found.",
            )

        if not account.is_active:
            raise BadRequestException(
                "Loyalty account is inactive.",
            )

        if account.points_balance < points:
            raise BadRequestException(
                "Insufficient loyalty points.",
            )

        # ------------------------------------------------------
        # Basic Idempotency
        # ------------------------------------------------------

        if (
            reference_type is not None
            and reference_id is not None
        ):
            existing_transactions = (
                await self.repository.get_by_reference(
                    reference_type=reference_type,
                    reference_id=reference_id,
                )
            )

            for transaction in existing_transactions:
                if (
                    transaction.transaction_type
                    == LoyaltyPointTransactionType.REDEEM
                ):
                    return transaction

        # ------------------------------------------------------
        # Update Balance
        # ------------------------------------------------------

        account.points_balance -= points

        # ------------------------------------------------------
        # Create Ledger Transaction
        # ------------------------------------------------------

        transaction = LoyaltyPointTransaction(
            loyalty_account_id=account.id,
            transaction_type=(
                LoyaltyPointTransactionType.REDEEM
            ),
            points=-points,
            balance_after=account.points_balance,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
        )

        await self.repository.save(
            transaction,
        )

        await self.db.commit()

        await self.db.refresh(
            transaction,
        )

        return transaction

    # ==========================================================
    # Point Adjustment
    # ==========================================================

    async def adjust_points(
        self,
        *,
        customer_id: int,
        points: int,
        description: str,
        reference_type: str | None = None,
        reference_id: int | None = None,
    ) -> LoyaltyPointTransaction:
        """
        Adjust a customer's loyalty point balance.

        Positive values add points.

        Negative values remove points.

        Lifetime points are increased only when the adjustment
        is positive.

        This operation is intended for controlled administrative
        or system corrections.

        Raises
        ------
        BadRequestException
            If the adjustment is zero, the account is inactive,
            or the adjustment would make the balance negative.

        NotFoundException
            If the loyalty account does not exist.
        """

        if points == 0:
            raise BadRequestException(
                "Point adjustment cannot be zero.",
            )

        account = await self.repository.get_by_customer_id(
            customer_id,
        )

        if account is None:
            raise NotFoundException(
                "Loyalty account not found.",
            )

        if not account.is_active:
            raise BadRequestException(
                "Loyalty account is inactive.",
            )

        new_balance = (
            account.points_balance + points
        )

        if new_balance < 0:
            raise BadRequestException(
                "Point adjustment would result in a negative "
                "loyalty balance.",
            )

        # ------------------------------------------------------
        # Update Balance
        # ------------------------------------------------------

        account.points_balance = new_balance

        if points > 0:
            account.lifetime_points += points

        # ------------------------------------------------------
        # Recalculate Tier
        # ------------------------------------------------------

        account.tier = self._determine_tier(
            account.lifetime_points,
        )

        # ------------------------------------------------------
        # Create Ledger Transaction
        # ------------------------------------------------------

        transaction = LoyaltyPointTransaction(
            loyalty_account_id=account.id,
            transaction_type=(
                LoyaltyPointTransactionType.ADJUSTMENT
            ),
            points=points,
            balance_after=account.points_balance,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
        )

        await self.repository.save(
            transaction,
        )

        await self.db.commit()

        await self.db.refresh(
            transaction,
        )

        return transaction

    # ==========================================================
    # Point Reversal
    # ==========================================================

    async def reverse_points(
        self,
        *,
        customer_id: int,
        points: int,
        description: str,
        reference_type: str | None = None,
        reference_id: int | None = None,
    ) -> LoyaltyPointTransaction:
        """
        Reverse previously awarded loyalty points.

        A reversal decreases the current points balance.

        Lifetime points are not reduced because lifetime points
        represent historical points earned by the customer.

        Raises
        ------
        BadRequestException
            If points are invalid, the account is inactive, or
            the reversal exceeds the current balance.

        NotFoundException
            If the loyalty account does not exist.
        """

        if points <= 0:
            raise BadRequestException(
                "Points to reverse must be greater than zero.",
            )

        account = await self.repository.get_by_customer_id(
            customer_id,
        )

        if account is None:
            raise NotFoundException(
                "Loyalty account not found.",
            )

        if not account.is_active:
            raise BadRequestException(
                "Loyalty account is inactive.",
            )

        if account.points_balance < points:
            raise BadRequestException(
                "Cannot reverse more loyalty points than "
                "the customer's current balance.",
            )

        # ------------------------------------------------------
        # Update Balance
        # ------------------------------------------------------

        account.points_balance -= points

        # ------------------------------------------------------
        # Recalculate Tier
        # ------------------------------------------------------

        account.tier = self._determine_tier(
            account.lifetime_points,
        )

        # ------------------------------------------------------
        # Create Ledger Transaction
        # ------------------------------------------------------

        transaction = LoyaltyPointTransaction(
            loyalty_account_id=account.id,
            transaction_type=(
                LoyaltyPointTransactionType.REVERSAL
            ),
            points=-points,
            balance_after=account.points_balance,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
        )

        await self.repository.save(
            transaction,
        )

        await self.db.commit()

        await self.db.refresh(
            transaction,
        )

        return transaction

    # ==========================================================
    # Read Operations
    # ==========================================================

    async def get_points_balance(
        self,
        customer_id: int,
    ) -> int:
        """
        Return the customer's current spendable point balance.
        """

        account = await self.get_account(
            customer_id,
        )

        return account.points_balance

    async def get_lifetime_points(
        self,
        customer_id: int,
    ) -> int:
        """
        Return the customer's lifetime earned points.
        """

        account = await self.get_account(
            customer_id,
        )

        return account.lifetime_points

    async def get_tier(
        self,
        customer_id: int,
    ) -> LoyaltyTier:
        """
        Return the customer's current loyalty tier.
        """

        account = await self.get_account(
            customer_id,
        )

        return account.tier

    async def get_point_history(
        self,
        customer_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyPointTransaction]:
        """
        Retrieve loyalty point transaction history.
        """

        if limit < 1:
            raise BadRequestException(
                "Limit must be greater than zero.",
            )

        if offset < 0:
            raise BadRequestException(
                "Offset cannot be negative.",
            )

        account = await self.get_account(
            customer_id,
        )

        return await self.repository.get_point_transactions(
            loyalty_account_id=account.id,
            limit=limit,
            offset=offset,
        )

    async def count_point_history(
        self,
        customer_id: int,
    ) -> int:
        """
        Return the number of point transactions belonging
        to the customer's loyalty account.
        """

        account = await self.get_account(
            customer_id,
        )

        return await self.repository.count_point_transactions(
            loyalty_account_id=account.id,
        )

    # ==========================================================
    # Tier Evaluation
    # ==========================================================

    def _determine_tier(
        self,
        lifetime_points: int,
    ) -> LoyaltyTier:
        """
        Determine the loyalty tier from lifetime points.

        Tier progression:

            0 - 999       -> BRONZE
            1,000 - 4,999 -> SILVER
            5,000 - 9,999 -> GOLD
            10,000+       -> PLATINUM
        """

        if lifetime_points >= self.PLATINUM_THRESHOLD:
            return LoyaltyTier.PLATINUM

        if lifetime_points >= self.GOLD_THRESHOLD:
            return LoyaltyTier.GOLD

        if lifetime_points >= self.SILVER_THRESHOLD:
            return LoyaltyTier.SILVER

        return LoyaltyTier.BRONZE