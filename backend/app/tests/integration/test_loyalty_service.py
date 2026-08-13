"""
Loyalty Service Integration Tests.

Tests the LoyaltyService against the real PostgreSQL test
database.

Architecture under test:

    Test
      |
      v
LoyaltyService
      |
      v
LoyaltyRepository
      |
      v
PostgreSQL

The tests intentionally do not involve:

- FastAPI
- PaymentService
- NotificationService
- Loyalty API routes

Those integrations will be tested later.

The purpose of this test suite is to verify the LoyaltyService
business rules using the real repository and database.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

from app.exceptions.handlers import (
    BadRequestException,
    NotFoundException,
)

from app.models.enums import (
    LoyaltyPointTransactionType,
    LoyaltyTier,
    UserRole,
)

from app.models.user import User

from app.repositories.loyalty_repository import (
    LoyaltyRepository,
)

from app.services.loyalty_service import (
    LoyaltyService,
)


# ==========================================================
# Test Database
# ==========================================================


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """
    Create a real asynchronous PostgreSQL test database
    session.
    """

    engine = create_async_engine(
        settings.TEST_DATABASE_URL,
        future=True,
    )

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()

    await engine.dispose()


# ==========================================================
# Service Fixture
# ==========================================================


@pytest_asyncio.fixture
async def loyalty_service(
    db_session: AsyncSession,
) -> LoyaltyService:
    """
    Create a real LoyaltyService backed by the real
    LoyaltyRepository and PostgreSQL test database.
    """

    repository = LoyaltyRepository(
        db=db_session,
    )

    return LoyaltyService(
        db=db_session,
        repository=repository,
    )


# ==========================================================
# Test User Factory
# ==========================================================


async def create_test_user(
    db: AsyncSession,
) -> User:
    """
    Create a real test user.
    """

    unique_id = uuid4().hex[:10].lower()

    user = User(
        first_name="Loyalty",
        last_name="Service Test",
        email=(
            f"loyalty.service.{unique_id}"
            "@test.local"
        ),
        phone_number=(
            f"0712{unique_id[:6]}"
        ),
        password_hash="integration-test-password-hash",
        role=UserRole.DRIVER,
        is_active=True,
        is_verified=True,
    )

    db.add(user)

    await db.flush()
    await db.refresh(user)

    return user


# ==========================================================
# Account Tests
# ==========================================================


@pytest.mark.asyncio
async def test_get_or_create_loyalty_account(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify that get_or_create_account() creates a new account
    with the correct initial values.
    """

    user = await create_test_user(
        db_session,
    )

    account = (
        await loyalty_service.get_or_create_account(
            user.id,
        )
    )

    assert account is not None
    assert account.id is not None
    assert account.customer_id == user.id
    assert account.points_balance == 0
    assert account.lifetime_points == 0
    assert account.tier == LoyaltyTier.BRONZE
    assert account.is_active is True

    print(
        "Create LoyaltyAccount through service: OK"
    )


@pytest.mark.asyncio
async def test_get_or_create_existing_account(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify that get_or_create_account() returns the existing
    account instead of creating a duplicate.
    """

    user = await create_test_user(
        db_session,
    )

    first = (
        await loyalty_service.get_or_create_account(
            user.id,
        )
    )

    second = (
        await loyalty_service.get_or_create_account(
            user.id,
        )
    )

    assert first.id == second.id
    assert second.customer_id == user.id

    print(
        "Existing LoyaltyAccount returned without duplication: OK"
    )


@pytest.mark.asyncio
async def test_get_account(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify retrieval of an existing loyalty account.
    """

    user = await create_test_user(
        db_session,
    )

    created = (
        await loyalty_service.get_or_create_account(
            user.id,
        )
    )

    retrieved = await loyalty_service.get_account(
        user.id,
    )

    assert retrieved.id == created.id
    assert retrieved.customer_id == user.id

    print(
        "Get LoyaltyAccount through service: OK"
    )


@pytest.mark.asyncio
async def test_get_account_not_found(
    loyalty_service: LoyaltyService,
):
    """
    Verify missing loyalty accounts raise NotFoundException.
    """

    with pytest.raises(
        NotFoundException,
        match="Loyalty account not found.",
    ):
        await loyalty_service.get_account(
            999999999,
        )

    print(
        "Missing LoyaltyAccount correctly rejected: OK"
    )


# ==========================================================
# Award Points
# ==========================================================


@pytest.mark.asyncio
async def test_award_points(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify awarding points updates:

    - points_balance
    - lifetime_points
    - tier
    - point ledger
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    transaction = await loyalty_service.award_points(
        customer_id=user.id,
        points=500,
        reference_type="PAYMENT_TRANSACTION",
        reference_id=1001,
        description="Test payment points",
    )

    assert transaction.id is not None
    assert transaction.transaction_type == (
        LoyaltyPointTransactionType.EARN
    )
    assert transaction.points == 500
    assert transaction.balance_after == 500

    account = await loyalty_service.get_account(
        user.id,
    )

    assert account.points_balance == 500
    assert account.lifetime_points == 500
    assert account.tier == LoyaltyTier.BRONZE

    print(
        "Award points: OK"
    )


@pytest.mark.asyncio
async def test_award_points_promotes_to_silver(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify promotion from BRONZE to SILVER.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    await loyalty_service.award_points(
        customer_id=user.id,
        points=1_000,
        reference_type="PAYMENT_TRANSACTION",
        reference_id=1002,
    )

    account = await loyalty_service.get_account(
        user.id,
    )

    assert account.points_balance == 1_000
    assert account.lifetime_points == 1_000
    assert account.tier == LoyaltyTier.SILVER

    print(
        "BRONZE -> SILVER promotion: OK"
    )


@pytest.mark.asyncio
async def test_award_points_promotes_to_gold(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify promotion from BRONZE to GOLD.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    await loyalty_service.award_points(
        customer_id=user.id,
        points=5_000,
        reference_type="PAYMENT_TRANSACTION",
        reference_id=1003,
    )

    account = await loyalty_service.get_account(
        user.id,
    )

    assert account.points_balance == 5_000
    assert account.lifetime_points == 5_000
    assert account.tier == LoyaltyTier.GOLD

    print(
        "BRONZE -> GOLD promotion: OK"
    )


@pytest.mark.asyncio
async def test_award_points_promotes_to_platinum(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify promotion from BRONZE to PLATINUM.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    await loyalty_service.award_points(
        customer_id=user.id,
        points=10_000,
        reference_type="PAYMENT_TRANSACTION",
        reference_id=1004,
    )

    account = await loyalty_service.get_account(
        user.id,
    )

    assert account.points_balance == 10_000
    assert account.lifetime_points == 10_000
    assert account.tier == LoyaltyTier.PLATINUM

    print(
        "BRONZE -> PLATINUM promotion: OK"
    )


@pytest.mark.asyncio
async def test_award_points_rejects_zero(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify zero points cannot be awarded.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    with pytest.raises(
        BadRequestException,
        match="Points to award must be greater than zero.",
    ):
        await loyalty_service.award_points(
            customer_id=user.id,
            points=0,
        )

    print(
        "Zero-point award correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_award_points_rejects_negative(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify negative points cannot be awarded.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    with pytest.raises(
        BadRequestException,
        match="Points to award must be greater than zero.",
    ):
        await loyalty_service.award_points(
            customer_id=user.id,
            points=-100,
        )

    print(
        "Negative-point award correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_award_points_requires_existing_account(
    loyalty_service: LoyaltyService,
):
    """
    Verify points cannot be awarded when the loyalty account
    does not exist.
    """

    with pytest.raises(
        NotFoundException,
        match="Loyalty account not found.",
    ):
        await loyalty_service.award_points(
            customer_id=999999999,
            points=100,
        )

    print(
        "Award without LoyaltyAccount correctly rejected: OK"
    )


# ==========================================================
# Award Idempotency
# ==========================================================


@pytest.mark.asyncio
async def test_award_points_idempotency(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify that the same business reference does not award
    points twice for the same transaction type.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    first = await loyalty_service.award_points(
        customer_id=user.id,
        points=300,
        reference_type="PAYMENT_TRANSACTION",
        reference_id=2001,
        description="First award",
    )

    second = await loyalty_service.award_points(
        customer_id=user.id,
        points=300,
        reference_type="PAYMENT_TRANSACTION",
        reference_id=2001,
        description="Duplicate award",
    )

    assert second.id == first.id

    account = await loyalty_service.get_account(
        user.id,
    )

    assert account.points_balance == 300
    assert account.lifetime_points == 300

    print(
        "Award point idempotency: OK"
    )


# ==========================================================
# Redemption
# ==========================================================


@pytest.mark.asyncio
async def test_redeem_points(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify redemption decreases the current balance but does
    not reduce lifetime points.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    await loyalty_service.award_points(
        customer_id=user.id,
        points=1_000,
        reference_type="PAYMENT_TRANSACTION",
        reference_id=3001,
    )

    transaction = await loyalty_service.redeem_points(
        customer_id=user.id,
        points=400,
        reference_type="REWARD_REDEMPTION",
        reference_id=4001,
        description="Test reward redemption",
    )

    assert transaction.transaction_type == (
        LoyaltyPointTransactionType.REDEEM
    )
    assert transaction.points == -400
    assert transaction.balance_after == 600

    account = await loyalty_service.get_account(
        user.id,
    )

    assert account.points_balance == 600
    assert account.lifetime_points == 1_000

    print(
        "Redeem points: OK"
    )


@pytest.mark.asyncio
async def test_redeem_points_rejects_insufficient_balance(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify redemption cannot exceed the current balance.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    await loyalty_service.award_points(
        customer_id=user.id,
        points=100,
    )

    with pytest.raises(
        BadRequestException,
        match="Insufficient loyalty points.",
    ):
        await loyalty_service.redeem_points(
            customer_id=user.id,
            points=101,
        )

    account = await loyalty_service.get_account(
        user.id,
    )

    assert account.points_balance == 100

    print(
        "Insufficient point redemption correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_redeem_points_rejects_zero(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify zero-point redemption is rejected.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    with pytest.raises(
        BadRequestException,
        match="Points to redeem must be greater than zero.",
    ):
        await loyalty_service.redeem_points(
            customer_id=user.id,
            points=0,
        )

    print(
        "Zero-point redemption correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_redeem_points_idempotency(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify the same redemption reference cannot redeem points
    twice.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    await loyalty_service.award_points(
        customer_id=user.id,
        points=1_000,
    )

    first = await loyalty_service.redeem_points(
        customer_id=user.id,
        points=250,
        reference_type="REWARD_REDEMPTION",
        reference_id=5001,
    )

    second = await loyalty_service.redeem_points(
        customer_id=user.id,
        points=250,
        reference_type="REWARD_REDEMPTION",
        reference_id=5001,
    )

    assert second.id == first.id

    account = await loyalty_service.get_account(
        user.id,
    )

    assert account.points_balance == 750

    print(
        "Redeem point idempotency: OK"
    )


# ==========================================================
# Adjustment
# ==========================================================


@pytest.mark.asyncio
async def test_adjust_points_positive(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify a positive adjustment increases balance and
    lifetime points.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    transaction = await loyalty_service.adjust_points(
        customer_id=user.id,
        points=250,
        description="Administrative loyalty adjustment",
        reference_type="ADMIN_ADJUSTMENT",
        reference_id=6001,
    )

    assert transaction.transaction_type == (
        LoyaltyPointTransactionType.ADJUSTMENT
    )
    assert transaction.points == 250
    assert transaction.balance_after == 250

    account = await loyalty_service.get_account(
        user.id,
    )

    assert account.points_balance == 250
    assert account.lifetime_points == 250

    print(
        "Positive point adjustment: OK"
    )


@pytest.mark.asyncio
async def test_adjust_points_negative(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify a negative adjustment decreases the balance but
    does not reduce lifetime points.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    await loyalty_service.award_points(
        customer_id=user.id,
        points=500,
    )

    transaction = await loyalty_service.adjust_points(
        customer_id=user.id,
        points=-200,
        description="Administrative correction",
        reference_type="ADMIN_ADJUSTMENT",
        reference_id=6002,
    )

    assert transaction.points == -200
    assert transaction.balance_after == 300

    account = await loyalty_service.get_account(
        user.id,
    )

    assert account.points_balance == 300
    assert account.lifetime_points == 500

    print(
        "Negative point adjustment: OK"
    )


@pytest.mark.asyncio
async def test_adjust_points_rejects_zero(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify zero-point adjustment is rejected.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    with pytest.raises(
        BadRequestException,
        match="Point adjustment cannot be zero.",
    ):
        await loyalty_service.adjust_points(
            customer_id=user.id,
            points=0,
            description="Invalid adjustment",
        )

    print(
        "Zero-point adjustment correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_adjust_points_cannot_make_balance_negative(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify an adjustment cannot produce a negative balance.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    await loyalty_service.award_points(
        customer_id=user.id,
        points=100,
    )

    with pytest.raises(
        BadRequestException,
        match="Point adjustment would result in a negative",
    ):
        await loyalty_service.adjust_points(
            customer_id=user.id,
            points=-101,
            description="Invalid negative adjustment",
        )

    account = await loyalty_service.get_account(
        user.id,
    )

    assert account.points_balance == 100

    print(
        "Negative-balance adjustment correctly rejected: OK"
    )


# ==========================================================
# Reversal
# ==========================================================


@pytest.mark.asyncio
async def test_reverse_points(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify point reversal decreases the current balance while
    preserving lifetime points.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    await loyalty_service.award_points(
        customer_id=user.id,
        points=1_000,
    )

    transaction = await loyalty_service.reverse_points(
        customer_id=user.id,
        points=300,
        description="Payment reversal",
        reference_type="PAYMENT_TRANSACTION",
        reference_id=7001,
    )

    assert transaction.transaction_type == (
        LoyaltyPointTransactionType.REVERSAL
    )
    assert transaction.points == -300
    assert transaction.balance_after == 700

    account = await loyalty_service.get_account(
        user.id,
    )

    assert account.points_balance == 700
    assert account.lifetime_points == 1_000

    print(
        "Reverse points: OK"
    )


@pytest.mark.asyncio
async def test_reverse_points_rejects_excessive_reversal(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify a reversal cannot exceed the current balance.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    await loyalty_service.award_points(
        customer_id=user.id,
        points=100,
    )

    with pytest.raises(
        BadRequestException,
        match="Cannot reverse more loyalty points",
    ):
        await loyalty_service.reverse_points(
            customer_id=user.id,
            points=101,
            description="Invalid reversal",
        )

    account = await loyalty_service.get_account(
        user.id,
    )

    assert account.points_balance == 100

    print(
        "Excessive point reversal correctly rejected: OK"
    )


# ==========================================================
# Read Operations
# ==========================================================


@pytest.mark.asyncio
async def test_get_points_balance(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify current point balance retrieval.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    await loyalty_service.award_points(
        customer_id=user.id,
        points=750,
    )

    balance = await loyalty_service.get_points_balance(
        user.id,
    )

    assert balance == 750

    print(
        "Get points balance: OK"
    )


@pytest.mark.asyncio
async def test_get_lifetime_points(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify lifetime point retrieval.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    await loyalty_service.award_points(
        customer_id=user.id,
        points=750,
    )

    await loyalty_service.redeem_points(
        customer_id=user.id,
        points=250,
    )

    lifetime = await loyalty_service.get_lifetime_points(
        user.id,
    )

    assert lifetime == 750

    print(
        "Get lifetime points: OK"
    )


@pytest.mark.asyncio
async def test_get_tier(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify current loyalty tier retrieval.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    await loyalty_service.award_points(
        customer_id=user.id,
        points=5_000,
    )

    tier = await loyalty_service.get_tier(
        user.id,
    )

    assert tier == LoyaltyTier.GOLD

    print(
        "Get loyalty tier: OK"
    )


@pytest.mark.asyncio
async def test_get_point_history(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify point history retrieval.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    await loyalty_service.award_points(
        customer_id=user.id,
        points=500,
    )

    await loyalty_service.redeem_points(
        customer_id=user.id,
        points=100,
    )

    history = await loyalty_service.get_point_history(
        user.id,
        limit=100,
        offset=0,
    )

    assert len(history) == 2

    transaction_types = {
        transaction.transaction_type
        for transaction in history
    }

    assert LoyaltyPointTransactionType.EARN in (
        transaction_types
    )

    assert LoyaltyPointTransactionType.REDEEM in (
        transaction_types
    )

    print(
        "Get point history: OK"
    )


@pytest.mark.asyncio
async def test_count_point_history(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify point history count.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    await loyalty_service.award_points(
        customer_id=user.id,
        points=100,
    )

    await loyalty_service.award_points(
        customer_id=user.id,
        points=200,
    )

    count = await loyalty_service.count_point_history(
        user.id,
    )

    assert count == 2

    print(
        "Count point history: OK"
    )


# ==========================================================
# Pagination Validation
# ==========================================================


@pytest.mark.asyncio
async def test_point_history_rejects_invalid_limit(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify invalid history limit is rejected.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    with pytest.raises(
        BadRequestException,
        match="Limit must be greater than zero.",
    ):
        await loyalty_service.get_point_history(
            user.id,
            limit=0,
        )

    print(
        "Invalid history limit correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_point_history_rejects_negative_offset(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify negative history offset is rejected.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    with pytest.raises(
        BadRequestException,
        match="Offset cannot be negative.",
    ):
        await loyalty_service.get_point_history(
            user.id,
            limit=100,
            offset=-1,
        )

    print(
        "Negative history offset correctly rejected: OK"
    )


# ==========================================================
# Inactive Account
# ==========================================================


@pytest.mark.asyncio
async def test_award_points_rejects_inactive_account(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify points cannot be awarded to an inactive account.
    """

    user = await create_test_user(
        db_session,
    )

    account = (
        await loyalty_service.get_or_create_account(
            user.id,
        )
    )

    account.is_active = False

    await db_session.commit()

    with pytest.raises(
        BadRequestException,
        match="Loyalty account is inactive.",
    ):
        await loyalty_service.award_points(
            customer_id=user.id,
            points=100,
        )

    print(
        "Inactive LoyaltyAccount correctly rejects award: OK"
    )


@pytest.mark.asyncio
async def test_redeem_points_rejects_inactive_account(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify points cannot be redeemed from an inactive account.
    """

    user = await create_test_user(
        db_session,
    )

    account = (
        await loyalty_service.get_or_create_account(
            user.id,
        )
    )

    account.is_active = False

    await db_session.commit()

    with pytest.raises(
        BadRequestException,
        match="Loyalty account is inactive.",
    ):
        await loyalty_service.redeem_points(
            customer_id=user.id,
            points=100,
        )

    print(
        "Inactive LoyaltyAccount correctly rejects redemption: OK"
    )


# ==========================================================
# Tier Determination
# ==========================================================


@pytest.mark.asyncio
async def test_tier_progression_across_multiple_awards(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Verify tier progression as lifetime points increase.
    """

    user = await create_test_user(
        db_session,
    )

    await loyalty_service.get_or_create_account(
        user.id,
    )

    # ------------------------------------------------------
    # BRONZE
    # ------------------------------------------------------

    await loyalty_service.award_points(
        customer_id=user.id,
        points=999,
    )

    account = await loyalty_service.get_account(
        user.id,
    )

    assert account.tier == LoyaltyTier.BRONZE

    # ------------------------------------------------------
    # SILVER
    # ------------------------------------------------------

    await loyalty_service.award_points(
        customer_id=user.id,
        points=1,
    )

    account = await loyalty_service.get_account(
        user.id,
    )

    assert account.lifetime_points == 1_000
    assert account.tier == LoyaltyTier.SILVER

    # ------------------------------------------------------
    # GOLD
    # ------------------------------------------------------

    await loyalty_service.award_points(
        customer_id=user.id,
        points=4_000,
    )

    account = await loyalty_service.get_account(
        user.id,
    )

    assert account.lifetime_points == 5_000
    assert account.tier == LoyaltyTier.GOLD

    # ------------------------------------------------------
    # PLATINUM
    # ------------------------------------------------------

    await loyalty_service.award_points(
        customer_id=user.id,
        points=5_000,
    )

    account = await loyalty_service.get_account(
        user.id,
    )

    assert account.lifetime_points == 10_000
    assert account.tier == LoyaltyTier.PLATINUM

    print(
        "BRONZE -> SILVER -> GOLD -> PLATINUM: OK"
    )


# ==========================================================
# Complete Service Integration Test
# ==========================================================


@pytest.mark.asyncio
async def test_loyalty_service_complete_integration(
    db_session: AsyncSession,
    loyalty_service: LoyaltyService,
):
    """
    Complete LoyaltyService business lifecycle.

    Workflow:

        Customer
            |
            v
        Loyalty Account
            |
            v
        Award Points
            |
            +------> Balance
            |
            +------> Lifetime Points
            |
            +------> Tier
            |
            v
        Redeem Points
            |
            v
        Adjust Points
            |
            v
        Reverse Points
            |
            v
        Point History
    """

    # ======================================================
    # 1. Customer
    # ======================================================

    user = await create_test_user(
        db_session,
    )

    print(
        f"Test customer created: {user.id}"
    )

    # ======================================================
    # 2. Create Loyalty Account
    # ======================================================

    account = (
        await loyalty_service.get_or_create_account(
            user.id,
        )
    )

    assert account.customer_id == user.id
    assert account.points_balance == 0
    assert account.lifetime_points == 0
    assert account.tier == LoyaltyTier.BRONZE

    print(
        "LoyaltyAccount creation: OK"
    )

    # ======================================================
    # 3. Award Points
    # ======================================================

    earn = await loyalty_service.award_points(
        customer_id=user.id,
        points=2_000,
        reference_type="PAYMENT_TRANSACTION",
        reference_id=9001,
        description="Parking payment loyalty points",
    )

    assert earn.points == 2_000
    assert earn.transaction_type == (
        LoyaltyPointTransactionType.EARN
    )

    account = await loyalty_service.get_account(
        user.id,
    )

    assert account.points_balance == 2_000
    assert account.lifetime_points == 2_000
    assert account.tier == LoyaltyTier.SILVER

    print(
        "Point awarding + tier evaluation: OK"
    )

    # ======================================================
    # 4. Redeem Points
    # ======================================================

    redeem = await loyalty_service.redeem_points(
        customer_id=user.id,
        points=500,
        reference_type="REWARD_REDEMPTION",
        reference_id=9002,
        description="Free parking reward",
    )

    assert redeem.points == -500
    assert redeem.transaction_type == (
        LoyaltyPointTransactionType.REDEEM
    )

    account = await loyalty_service.get_account(
        user.id,
    )

    assert account.points_balance == 1_500
    assert account.lifetime_points == 2_000

    print(
        "Point redemption: OK"
    )

    # ======================================================
    # 5. Positive Adjustment
    # ======================================================

    adjustment = await loyalty_service.adjust_points(
        customer_id=user.id,
        points=250,
        description="Customer service adjustment",
        reference_type="ADMIN_ADJUSTMENT",
        reference_id=9003,
    )

    assert adjustment.points == 250
    assert adjustment.transaction_type == (
        LoyaltyPointTransactionType.ADJUSTMENT
    )

    account = await loyalty_service.get_account(
        user.id,
    )

    assert account.points_balance == 1_750
    assert account.lifetime_points == 2_250

    print(
        "Positive point adjustment: OK"
    )

    # ======================================================
    # 6. Reverse Points
    # ======================================================

    reversal = await loyalty_service.reverse_points(
        customer_id=user.id,
        points=250,
        description="Payment reversal",
        reference_type="PAYMENT_TRANSACTION",
        reference_id=9004,
    )

    assert reversal.points == -250
    assert reversal.transaction_type == (
        LoyaltyPointTransactionType.REVERSAL
    )

    account = await loyalty_service.get_account(
        user.id,
    )

    assert account.points_balance == 1_500
    assert account.lifetime_points == 2_250

    print(
        "Point reversal: OK"
    )

    # ======================================================
    # 7. History
    # ======================================================

    history = await loyalty_service.get_point_history(
        user.id,
        limit=100,
        offset=0,
    )

    assert len(history) == 4

    print(
        "Point history retrieval: OK"
    )

    # ======================================================
    # 8. Count
    # ======================================================

    count = await loyalty_service.count_point_history(
        user.id,
    )

    assert count == 4

    print(
        "Point history count: OK"
    )

    # ======================================================
    # 9. Balance
    # ======================================================

    balance = await loyalty_service.get_points_balance(
        user.id,
    )

    assert balance == 1_500

    print(
        "Current points balance: OK"
    )

    # ======================================================
    # 10. Lifetime Points
    # ======================================================

    lifetime = await loyalty_service.get_lifetime_points(
        user.id,
    )

    assert lifetime == 2_250

    print(
        "Lifetime points: OK"
    )

    # ======================================================
    # 11. Tier
    # ======================================================

    tier = await loyalty_service.get_tier(
        user.id,
    )

    assert tier == LoyaltyTier.SILVER

    print(
        "Current loyalty tier: OK"
    )

    # ======================================================
    # Final Result
    # ======================================================

    print(
        "\n"
        "====================================================\n"
        "Loyalty Service Integration Test\n"
        "SERVICE -> REPOSITORY -> POSTGRESQL\n"
        "INTEGRATION TEST: PASSED\n"
        "===================================================="
    )