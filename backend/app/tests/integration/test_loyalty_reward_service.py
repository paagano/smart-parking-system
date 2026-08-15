"""
Loyalty Reward Service Integration Tests.

Tests the LoyaltyRewardService against the real PostgreSQL
test database.

Architecture under test:

    Test
      |
      v
    LoyaltyRewardService
      |
      +----------------------+
      |                      |
      v                      v
LoyaltyRewardRepository   LoyaltyService
      |                      |
      +----------+-----------+
                 |
                 v
             PostgreSQL

The tests intentionally do not involve:

- FastAPI
- Loyalty Reward API routes
- PaymentService
- NotificationService
- React/frontend

The purpose of this suite is to verify the LoyaltyRewardService
business rules using the real repositories and PostgreSQL test
database.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
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
    LoyaltyRewardStatus,
    LoyaltyRewardType,
    LoyaltyTier,
    RewardRedemptionStatus,
    UserRole,
)

from app.models.loyalty_reward import (
    LoyaltyReward,
)

from app.models.loyalty_reward_redemption import (
    LoyaltyRewardRedemption,
)

from app.models.loyalty_account import (
    LoyaltyAccount,
)

from app.models.user import (
    User,
)

from app.repositories.loyalty_repository import (
    LoyaltyRepository,
)

from app.repositories.loyalty_reward_repository import (
    LoyaltyRewardRepository,
)

from app.services.loyalty_service import (
    LoyaltyService,
)

from app.services.loyalty_reward_service import (
    LoyaltyRewardService,
)

def utc_now_naive() -> datetime:
    """
    Return the current UTC datetime without timezone information.

    The loyalty_rewards.valid_from and valid_until columns are
    PostgreSQL TIMESTAMP WITHOUT TIME ZONE.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
async def loyalty_reward_service(
    db_session: AsyncSession,
) -> LoyaltyRewardService:
    """
    Create a real LoyaltyRewardService backed by:

        LoyaltyRewardRepository
        LoyaltyRepository
        PostgreSQL
    """

    reward_repository = LoyaltyRewardRepository(
        db=db_session,
    )

    loyalty_repository = LoyaltyRepository(
        db=db_session,
    )

    loyalty_service = LoyaltyService(
        db=db_session,
        repository=loyalty_repository,
    )

    return LoyaltyRewardService(
        db=db_session,
        repository=reward_repository,
        loyalty_service=loyalty_service,
    )


# ==========================================================
# Test User Factory
# ==========================================================


async def create_test_user(
    db: AsyncSession,
    *,
    email: str | None = None,
) -> User:
    """
    Create a real test user with unique email and phone number.
    """

    unique_id = uuid4().hex[:10].lower()

    if email is None:
        email = (
            f"loyalty.reward.service."
            f"{unique_id}@test.local"
        )

    user = User(
        first_name="Loyalty",
        last_name="Reward Test",
        email=email,
        phone_number=f"0712{unique_id[:6]}",
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
# Loyalty Account Factory
# ==========================================================


async def create_test_loyalty_account(
    db: AsyncSession,
    *,
    customer_id: int,
    points_balance: int = 0,
    lifetime_points: int = 0,
    tier: LoyaltyTier = LoyaltyTier.BRONZE,
    is_active: bool = True,
) -> LoyaltyAccount:
    """
    Create a real LoyaltyAccount for testing.
    """

    account = LoyaltyAccount(
        customer_id=customer_id,
        points_balance=points_balance,
        lifetime_points=lifetime_points,
        tier=tier,
        is_active=is_active,
    )

    db.add(account)

    await db.flush()
    await db.refresh(account)

    return account


# ==========================================================
# Reward Factory
# ==========================================================


async def create_test_reward(
    db: AsyncSession,
    *,
    name: str | None = None,
    reward_type: LoyaltyRewardType = (
        LoyaltyRewardType.DISCOUNT
    ),
    points_cost: int = 500,
    monetary_value: Decimal | None = Decimal("100.00"),
    status: LoyaltyRewardStatus = (
        LoyaltyRewardStatus.ACTIVE
    ),
    is_active: bool = True,
    minimum_tier: LoyaltyTier | None = None,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
) -> LoyaltyReward:
    """
    Create a real LoyaltyReward for testing.

    The database columns valid_from and valid_until are
    TIMESTAMP WITHOUT TIME ZONE, so timezone-aware datetimes
    are normalized to UTC-naive values.
    """

    unique_id = uuid4().hex[:8].upper()

    if name is None:
        name = f"Test Reward {unique_id}"

    if valid_from is not None:
        if valid_from.tzinfo is not None:
            valid_from = (
                valid_from
                .astimezone()
                .replace(tzinfo=None)
            )

    if valid_until is not None:
        if valid_until.tzinfo is not None:
            valid_until = (
                valid_until
                .astimezone()
                .replace(tzinfo=None)
            )

    reward = LoyaltyReward(
        name=name,
        description=f"Integration test reward {unique_id}",
        reward_type=reward_type,
        points_cost=points_cost,
        monetary_value=monetary_value,
        status=status,
        is_active=is_active,
        minimum_tier=minimum_tier,
        valid_from=valid_from,
        valid_until=valid_until,
    )

    db.add(reward)

    await db.flush()
    await db.refresh(reward)

    return reward


# ==========================================================
# Account Tests
# ==========================================================


@pytest.mark.asyncio
async def test_get_reward(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify retrieval of a reward by ID.
    """

    reward = await create_test_reward(
        db_session,
        name="Get Reward",
    )

    retrieved = await loyalty_reward_service.get_reward(
        reward.id,
    )

    assert retrieved.id == reward.id
    assert retrieved.name == "Get Reward"

    print(
        "Get LoyaltyReward through service: OK"
    )


@pytest.mark.asyncio
async def test_get_reward_not_found(
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify missing rewards raise NotFoundException.
    """

    with pytest.raises(
        NotFoundException,
        match="Loyalty reward not found.",
    ):
        await loyalty_reward_service.get_reward(
            999999999,
        )

    print(
        "Missing LoyaltyReward correctly rejected: OK"
    )


# ==========================================================
# Reward Catalogue
# ==========================================================


@pytest.mark.asyncio
async def test_get_active_reward(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify active reward retrieval.
    """

    reward = await create_test_reward(
        db_session,
        name="Active Reward",
    )

    retrieved = (
        await loyalty_reward_service.get_active_reward(
            reward.id,
        )
    )

    assert retrieved.id == reward.id
    assert retrieved.is_active is True
    assert retrieved.status == LoyaltyRewardStatus.ACTIVE

    print(
        "Get active LoyaltyReward through service: OK"
    )


@pytest.mark.asyncio
async def test_get_active_reward_rejects_inactive(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify inactive rewards are not returned as active.
    """

    reward = await create_test_reward(
        db_session,
        name="Inactive Reward",
        is_active=False,
    )

    with pytest.raises(
        NotFoundException,
        match="Active loyalty reward not found.",
    ):
        await loyalty_reward_service.get_active_reward(
            reward.id,
        )

    print(
        "Inactive LoyaltyReward correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_get_all_rewards(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify paginated reward retrieval.
    """

    await create_test_reward(
        db_session,
        name="Catalogue Reward A",
    )

    await create_test_reward(
        db_session,
        name="Catalogue Reward B",
    )

    results = await loyalty_reward_service.get_all_rewards(
        limit=2,
        offset=0,
    )

    assert len(results) <= 2

    print(
        "Get all LoyaltyRewards with pagination: OK"
    )


@pytest.mark.asyncio
async def test_get_active_rewards(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify active reward retrieval.
    """

    active_reward = await create_test_reward(
        db_session,
        name="Active Catalogue Reward",
        is_active=True,
    )

    await create_test_reward(
        db_session,
        name="Inactive Catalogue Reward",
        is_active=False,
    )

    results = await loyalty_reward_service.get_active_rewards()

    ids = {
        reward.id
        for reward in results
    }

    assert active_reward.id in ids

    assert all(
        reward.is_active is True
        for reward in results
    )

    print(
        "Get active LoyaltyRewards: OK"
    )


@pytest.mark.asyncio
async def test_get_rewards_by_type(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify reward type filtering.
    """

    reward = await create_test_reward(
        db_session,
        name="Free Parking Reward",
        reward_type=LoyaltyRewardType.FREE_PARKING,
    )

    await create_test_reward(
        db_session,
        name="Discount Reward",
        reward_type=LoyaltyRewardType.DISCOUNT,
    )

    results = (
        await loyalty_reward_service.get_rewards_by_type(
            LoyaltyRewardType.FREE_PARKING,
        )
    )

    ids = {
        item.id
        for item in results
    }

    assert reward.id in ids

    assert all(
        item.reward_type
        == LoyaltyRewardType.FREE_PARKING
        for item in results
    )

    print(
        "Filter LoyaltyRewards by type: OK"
    )


# ==========================================================
# Reward Creation
# ==========================================================


@pytest.mark.asyncio
async def test_create_reward(
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify reward creation through the service.
    """

    reward = await loyalty_reward_service.create_reward(
        name="Created Service Reward",
        description="Created through service",
        reward_type=LoyaltyRewardType.DISCOUNT,
        points_cost=750,
        monetary_value=Decimal("150.00"),
        minimum_tier=LoyaltyTier.SILVER,
    )

    assert reward.id is not None
    assert reward.name == "Created Service Reward"
    assert reward.points_cost == 750
    assert reward.monetary_value == Decimal("150.00")
    assert reward.minimum_tier == LoyaltyTier.SILVER
    assert reward.status == LoyaltyRewardStatus.ACTIVE
    assert reward.is_active is True

    print(
        "Create LoyaltyReward through service: OK"
    )


@pytest.mark.asyncio
async def test_create_reward_rejects_zero_points(
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify zero-point rewards are rejected.
    """

    with pytest.raises(
        BadRequestException,
        match="Reward points cost must be greater than zero.",
    ):
        await loyalty_reward_service.create_reward(
            name="Invalid Reward",
            description=None,
            reward_type=LoyaltyRewardType.DISCOUNT,
            points_cost=0,
        )

    print(
        "Zero-point reward correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_create_reward_rejects_negative_points(
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify negative-point rewards are rejected.
    """

    with pytest.raises(
        BadRequestException,
        match="Reward points cost must be greater than zero.",
    ):
        await loyalty_reward_service.create_reward(
            name="Invalid Reward",
            description=None,
            reward_type=LoyaltyRewardType.DISCOUNT,
            points_cost=-100,
        )

    print(
        "Negative-point reward correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_create_reward_rejects_invalid_dates(
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify invalid reward validity periods are rejected.
    """

    now = datetime.now(
        timezone.utc,
    )

    with pytest.raises(
        BadRequestException,
        match=(
            "Reward valid_until cannot be earlier "
            "than valid_from."
        ),
    ):
        await loyalty_reward_service.create_reward(
            name="Invalid Date Reward",
            description=None,
            reward_type=LoyaltyRewardType.DISCOUNT,
            points_cost=500,
            valid_from=now,
            valid_until=now - timedelta(days=1),
        )

    print(
        "Invalid reward validity period correctly rejected: OK"
    )


# ==========================================================
# Reward Update
# ==========================================================


@pytest.mark.asyncio
async def test_update_reward(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify reward update.
    """

    reward = await create_test_reward(
        db_session,
        name="Original Reward",
        points_cost=500,
    )

    updated = await loyalty_reward_service.update_reward(
        reward.id,
        name="Updated Reward",
        points_cost=750,
        monetary_value=Decimal("200.00"),
    )

    assert updated.id == reward.id
    assert updated.name == "Updated Reward"
    assert updated.points_cost == 750
    assert updated.monetary_value == Decimal("200.00")

    print(
        "Update LoyaltyReward: OK"
    )


@pytest.mark.asyncio
async def test_update_reward_rejects_zero_points(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify invalid reward point costs are rejected during update.
    """

    reward = await create_test_reward(
        db_session,
        name="Update Validation Reward",
    )

    with pytest.raises(
        BadRequestException,
        match="Reward points cost must be greater than zero.",
    ):
        await loyalty_reward_service.update_reward(
            reward.id,
            points_cost=0,
        )

    print(
        "Invalid reward update correctly rejected: OK"
    )


# ==========================================================
# Eligibility
# ==========================================================


@pytest.mark.asyncio
async def test_get_eligible_rewards_for_bronze_customer(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify BRONZE customers receive BRONZE-level rewards.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        tier=LoyaltyTier.BRONZE,
    )

    bronze_reward = await create_test_reward(
        db_session,
        name="Bronze Reward",
        minimum_tier=LoyaltyTier.BRONZE,
    )

    gold_reward = await create_test_reward(
        db_session,
        name="Gold Reward",
        minimum_tier=LoyaltyTier.GOLD,
    )

    results = (
        await loyalty_reward_service.get_eligible_rewards(
            customer_id=user.id,
        )
    )

    ids = {
        reward.id
        for reward in results
    }

    assert bronze_reward.id in ids
    assert gold_reward.id not in ids

    print(
        "BRONZE reward eligibility: OK"
    )


@pytest.mark.asyncio
async def test_get_eligible_rewards_for_gold_customer(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify GOLD customers receive BRONZE, SILVER and GOLD
    rewards, but not PLATINUM rewards.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        tier=LoyaltyTier.GOLD,
    )

    bronze_reward = await create_test_reward(
        db_session,
        name="Bronze Eligible Reward",
        minimum_tier=LoyaltyTier.BRONZE,
    )

    silver_reward = await create_test_reward(
        db_session,
        name="Silver Eligible Reward",
        minimum_tier=LoyaltyTier.SILVER,
    )

    gold_reward = await create_test_reward(
        db_session,
        name="Gold Eligible Reward",
        minimum_tier=LoyaltyTier.GOLD,
    )

    platinum_reward = await create_test_reward(
        db_session,
        name="Platinum Reward",
        minimum_tier=LoyaltyTier.PLATINUM,
    )

    results = (
        await loyalty_reward_service.get_eligible_rewards(
            customer_id=user.id,
        )
    )

    ids = {
        reward.id
        for reward in results
    }

    assert bronze_reward.id in ids
    assert silver_reward.id in ids
    assert gold_reward.id in ids
    assert platinum_reward.id not in ids

    print(
        "GOLD reward eligibility: OK"
    )


@pytest.mark.asyncio
async def test_get_eligible_rewards_includes_no_tier_rewards(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify rewards with no minimum tier are available to all
    loyalty tiers.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        tier=LoyaltyTier.BRONZE,
    )

    reward = await create_test_reward(
        db_session,
        name="Universal Reward",
        minimum_tier=None,
    )

    results = (
        await loyalty_reward_service.get_eligible_rewards(
            customer_id=user.id,
        )
    )

    ids = {
        item.id
        for item in results
    }

    assert reward.id in ids

    print(
        "Universal reward eligibility: OK"
    )


# ==========================================================
# Reward Validity
# ==========================================================


@pytest.mark.asyncio
async def test_expired_reward_cannot_be_redeemed(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify expired rewards cannot be redeemed.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        points_balance=1000,
        lifetime_points=1000,
        tier=LoyaltyTier.SILVER,
    )

    expired_reward = await create_test_reward(
        db_session,
        name="Expired Reward",
        points_cost=500,
        valid_until=(
            utc_now_naive()
            - timedelta(days=1)
        ),
    )

    with pytest.raises(
        BadRequestException,
        match=(
            "This loyalty reward is outside its "
            "valid redemption period."
        ),
    ):
        await loyalty_reward_service.redeem_reward(
            customer_id=user.id,
            reward_id=expired_reward.id,
        )

    print(
        "Expired reward correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_future_reward_cannot_be_redeemed(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify rewards whose valid_from is in the future cannot
    be redeemed.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        points_balance=1000,
        lifetime_points=1000,
        tier=LoyaltyTier.SILVER,
    )

    future_reward = await create_test_reward(
        db_session,
        name="Future Reward",
        points_cost=500,
        valid_from=(
            utc_now_naive()
            + timedelta(days=1)
        ),
    )

    with pytest.raises(
        BadRequestException,
        match=(
            "This loyalty reward is outside its "
            "valid redemption period."
        ),
    ):
        await loyalty_reward_service.redeem_reward(
            customer_id=user.id,
            reward_id=future_reward.id,
        )

    print(
        "Future reward correctly rejected: OK"
    )


# ==========================================================
# Redemption Validation
# ==========================================================


@pytest.mark.asyncio
async def test_redeem_reward_requires_existing_account(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify reward redemption requires a loyalty account.
    """

    user = await create_test_user(
        db_session,
    )

    reward = await create_test_reward(
        db_session,
        name="No Account Reward",
        points_cost=500,
    )

    with pytest.raises(
        NotFoundException,
        match="Loyalty account not found.",
    ):
        await loyalty_reward_service.redeem_reward(
            customer_id=user.id,
            reward_id=reward.id,
        )

    print(
        "Redemption without LoyaltyAccount correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_redeem_reward_rejects_inactive_account(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify inactive loyalty accounts cannot redeem rewards.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        points_balance=1000,
        lifetime_points=1000,
        tier=LoyaltyTier.SILVER,
        is_active=False,
    )

    reward = await create_test_reward(
        db_session,
        name="Inactive Account Reward",
        points_cost=500,
    )

    with pytest.raises(
        BadRequestException,
        match="Loyalty account is inactive.",
    ):
        await loyalty_reward_service.redeem_reward(
            customer_id=user.id,
            reward_id=reward.id,
        )

    print(
        "Inactive LoyaltyAccount correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_redeem_reward_requires_active_reward(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify inactive rewards cannot be redeemed.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        points_balance=1000,
        lifetime_points=1000,
        tier=LoyaltyTier.SILVER,
    )

    reward = await create_test_reward(
        db_session,
        name="Inactive Redemption Reward",
        points_cost=500,
        is_active=False,
    )

    with pytest.raises(
        NotFoundException,
        match="Active loyalty reward not found.",
    ):
        await loyalty_reward_service.redeem_reward(
            customer_id=user.id,
            reward_id=reward.id,
        )

    print(
        "Inactive reward redemption correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_redeem_reward_rejects_insufficient_points(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify customers cannot redeem rewards they cannot afford.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        points_balance=100,
        lifetime_points=100,
        tier=LoyaltyTier.BRONZE,
    )

    reward = await create_test_reward(
        db_session,
        name="Expensive Reward",
        points_cost=500,
    )

    with pytest.raises(
        BadRequestException,
        match="Insufficient loyalty points",
    ):
        await loyalty_reward_service.redeem_reward(
            customer_id=user.id,
            reward_id=reward.id,
        )

    print(
        "Insufficient loyalty points correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_redeem_reward_rejects_ineligible_tier(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify customers cannot redeem rewards above their tier.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        points_balance=5000,
        lifetime_points=500,
        tier=LoyaltyTier.BRONZE,
    )

    reward = await create_test_reward(
        db_session,
        name="Platinum Reward",
        points_cost=500,
        minimum_tier=LoyaltyTier.PLATINUM,
    )

    with pytest.raises(
        BadRequestException,
        match=(
            "Customer loyalty tier is not eligible "
            "for this reward."
        ),
    ):
        await loyalty_reward_service.redeem_reward(
            customer_id=user.id,
            reward_id=reward.id,
        )

    print(
        "Ineligible loyalty tier correctly rejected: OK"
    )


# ==========================================================
# Successful Redemption
# ==========================================================


@pytest.mark.asyncio
async def test_redeem_reward(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify successful reward redemption.

    Covers:

        Customer
            ↓
        LoyaltyAccount
            ↓
        Reward
            ↓
        LoyaltyService.redeem_points()
            ↓
        LoyaltyPointTransaction
            ↓
        LoyaltyRewardRedemption
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        points_balance=1000,
        lifetime_points=1500,
        tier=LoyaltyTier.SILVER,
    )

    reward = await create_test_reward(
        db_session,
        name="One Hour Free Parking",
        reward_type=LoyaltyRewardType.FREE_PARKING,
        points_cost=500,
        minimum_tier=LoyaltyTier.BRONZE,
    )

    (
        redemption,
        returned_reward,
        remaining_points,
        tier,
    ) = await loyalty_reward_service.redeem_reward(
        customer_id=user.id,
        reward_id=reward.id,
    )

    assert redemption.id is not None
    assert redemption.loyalty_account_id is not None
    assert redemption.reward_id == reward.id
    assert redemption.points_spent == 500
    assert (
        redemption.status
        == RewardRedemptionStatus.REDEEMED
    )
    assert redemption.redemption_reference.startswith(
        "SPR-REWARD-"
    )

    assert returned_reward.id == reward.id
    assert remaining_points == 500
    assert tier == LoyaltyTier.SILVER

    print(
        "Reward redemption: OK"
    )


@pytest.mark.asyncio
async def test_redeem_reward_creates_redemption_record(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify the actual LoyaltyRewardRedemption record is
    persisted.
    """

    user = await create_test_user(
        db_session,
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        points_balance=1000,
        lifetime_points=1000,
        tier=LoyaltyTier.SILVER,
    )

    reward = await create_test_reward(
        db_session,
        name="Persisted Redemption Reward",
        points_cost=500,
    )

    (
        redemption,
        _,
        remaining_points,
        _,
    ) = await loyalty_reward_service.redeem_reward(
        customer_id=user.id,
        reward_id=reward.id,
    )

    assert redemption.id is not None
    assert redemption.loyalty_account_id == account.id
    assert redemption.reward_id == reward.id
    assert remaining_points == 500

    await db_session.refresh(
        redemption,
    )

    assert redemption.points_spent == 500

    print(
        "LoyaltyRewardRedemption persistence: OK"
    )


@pytest.mark.asyncio
async def test_redeem_reward_deducts_points(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify reward redemption deducts points from the customer's
    spendable balance.
    """

    user = await create_test_user(
        db_session,
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        points_balance=1500,
        lifetime_points=2000,
        tier=LoyaltyTier.SILVER,
    )

    reward = await create_test_reward(
        db_session,
        name="Point Deduction Reward",
        points_cost=750,
    )

    await loyalty_reward_service.redeem_reward(
        customer_id=user.id,
        reward_id=reward.id,
    )

    await db_session.refresh(
        account,
    )

    assert account.points_balance == 750

    # Lifetime points must not decrease.
    assert account.lifetime_points == 2000

    print(
        "Reward point deduction: OK"
    )


# ==========================================================
# Redemption Reference
# ==========================================================


@pytest.mark.asyncio
async def test_redemption_reference_is_unique(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify redemption references are generated uniquely.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        points_balance=2000,
        lifetime_points=2000,
        tier=LoyaltyTier.SILVER,
    )

    reward_a = await create_test_reward(
        db_session,
        name="Reference Reward A",
        points_cost=500,
    )

    reward_b = await create_test_reward(
        db_session,
        name="Reference Reward B",
        points_cost=500,
    )

    redemption_a, _, _, _ = (
        await loyalty_reward_service.redeem_reward(
            customer_id=user.id,
            reward_id=reward_a.id,
        )
    )

    redemption_b, _, _, _ = (
        await loyalty_reward_service.redeem_reward(
            customer_id=user.id,
            reward_id=reward_b.id,
        )
    )

    assert (
        redemption_a.redemption_reference
        != redemption_b.redemption_reference
    )

    print(
        "Unique redemption references: OK"
    )


# ==========================================================
# Redemption History
# ==========================================================


@pytest.mark.asyncio
async def test_get_redemption(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify redemption retrieval by ID.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        points_balance=1000,
        lifetime_points=1000,
        tier=LoyaltyTier.SILVER,
    )

    reward = await create_test_reward(
        db_session,
        name="Get Redemption Reward",
        points_cost=500,
    )

    redemption, _, _, _ = (
        await loyalty_reward_service.redeem_reward(
            customer_id=user.id,
            reward_id=reward.id,
        )
    )

    retrieved = (
        await loyalty_reward_service.get_redemption(
            redemption.id,
        )
    )

    assert retrieved.id == redemption.id
    assert (
        retrieved.redemption_reference
        == redemption.redemption_reference
    )

    print(
        "Get reward redemption: OK"
    )


@pytest.mark.asyncio
async def test_get_redemption_not_found(
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify missing redemptions raise NotFoundException.
    """

    with pytest.raises(
        NotFoundException,
        match="Loyalty reward redemption not found.",
    ):
        await loyalty_reward_service.get_redemption(
            999999999,
        )

    print(
        "Missing redemption correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_get_redemption_by_reference(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify redemption retrieval by unique reference.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        points_balance=1000,
        lifetime_points=1000,
        tier=LoyaltyTier.SILVER,
    )

    reward = await create_test_reward(
        db_session,
        name="Reference Lookup Reward",
        points_cost=500,
    )

    redemption, _, _, _ = (
        await loyalty_reward_service.redeem_reward(
            customer_id=user.id,
            reward_id=reward.id,
        )
    )

    retrieved = (
        await loyalty_reward_service
        .get_redemption_by_reference(
            redemption.redemption_reference,
        )
    )

    assert retrieved.id == redemption.id

    print(
        "Redemption reference lookup: OK"
    )


@pytest.mark.asyncio
async def test_get_customer_redemptions(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify customer redemption history.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        points_balance=2000,
        lifetime_points=2000,
        tier=LoyaltyTier.SILVER,
    )

    reward_a = await create_test_reward(
        db_session,
        name="History Reward A",
        points_cost=500,
    )

    reward_b = await create_test_reward(
        db_session,
        name="History Reward B",
        points_cost=500,
    )

    await loyalty_reward_service.redeem_reward(
        customer_id=user.id,
        reward_id=reward_a.id,
    )

    await loyalty_reward_service.redeem_reward(
        customer_id=user.id,
        reward_id=reward_b.id,
    )

    results = (
        await loyalty_reward_service.get_customer_redemptions(
            customer_id=user.id,
        )
    )

    assert len(results) >= 2

    assert all(
        redemption.loyalty_account_id is not None
        for redemption in results
    )

    print(
        "Customer reward redemption history: OK"
    )


@pytest.mark.asyncio
async def test_count_customer_redemptions(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify customer redemption count.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        points_balance=1500,
        lifetime_points=1500,
        tier=LoyaltyTier.SILVER,
    )

    reward_a = await create_test_reward(
        db_session,
        name="Count Reward A",
        points_cost=500,
    )

    reward_b = await create_test_reward(
        db_session,
        name="Count Reward B",
        points_cost=500,
    )

    await loyalty_reward_service.redeem_reward(
        customer_id=user.id,
        reward_id=reward_a.id,
    )

    await loyalty_reward_service.redeem_reward(
        customer_id=user.id,
        reward_id=reward_b.id,
    )

    count = (
        await loyalty_reward_service
        .count_customer_redemptions(
            customer_id=user.id,
        )
    )

    assert count >= 2

    print(
        "Customer redemption count: OK"
    )


# ==========================================================
# Reward Redemption History
# ==========================================================


@pytest.mark.asyncio
async def test_get_reward_redemptions(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify redemption history for a specific reward.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        points_balance=1000,
        lifetime_points=1000,
        tier=LoyaltyTier.SILVER,
    )

    reward = await create_test_reward(
        db_session,
        name="Reward History",
        points_cost=500,
    )

    await loyalty_reward_service.redeem_reward(
        customer_id=user.id,
        reward_id=reward.id,
    )

    results = (
        await loyalty_reward_service.get_reward_redemptions(
            reward.id,
        )
    )

    assert len(results) >= 1

    assert all(
        redemption.reward_id == reward.id
        for redemption in results
    )

    print(
        "Reward redemption history: OK"
    )


@pytest.mark.asyncio
async def test_count_reward_redemptions(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify redemption count for a reward.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        points_balance=1000,
        lifetime_points=1000,
        tier=LoyaltyTier.SILVER,
    )

    reward = await create_test_reward(
        db_session,
        name="Reward Count",
        points_cost=500,
    )

    await loyalty_reward_service.redeem_reward(
        customer_id=user.id,
        reward_id=reward.id,
    )

    count = (
        await loyalty_reward_service
        .count_reward_redemptions(
            reward.id,
        )
    )

    assert count >= 1

    print(
        "Reward redemption count: OK"
    )


# ==========================================================
# Pagination Validation
# ==========================================================


@pytest.mark.asyncio
async def test_reward_history_rejects_invalid_limit(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify invalid redemption history limits are rejected.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    with pytest.raises(
        BadRequestException,
        match="Limit must be greater than zero.",
    ):
        await loyalty_reward_service.get_customer_redemptions(
            customer_id=user.id,
            limit=0,
        )

    print(
        "Invalid redemption history limit correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_reward_history_rejects_negative_offset(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify negative redemption history offsets are rejected.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    with pytest.raises(
        BadRequestException,
        match="Offset cannot be negative.",
    ):
        await loyalty_reward_service.get_customer_redemptions(
            customer_id=user.id,
            offset=-1,
        )

    print(
        "Negative redemption history offset correctly rejected: OK"
    )


# ==========================================================
# Active Redemption
# ==========================================================


@pytest.mark.asyncio
async def test_get_active_redemption(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Verify retrieval of an active/redeemed reward redemption.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        points_balance=1000,
        lifetime_points=1000,
        tier=LoyaltyTier.SILVER,
    )

    reward = await create_test_reward(
        db_session,
        name="Active Redemption Reward",
        points_cost=500,
    )

    redemption, _, _, _ = (
        await loyalty_reward_service.redeem_reward(
            customer_id=user.id,
            reward_id=reward.id,
        )
    )

    retrieved = (
        await loyalty_reward_service.get_active_redemption(
            redemption.id,
        )
    )

    assert retrieved.id == redemption.id
    assert (
        retrieved.status
        == RewardRedemptionStatus.REDEEMED
    )

    print(
        "Active reward redemption lookup: OK"
    )


# ==========================================================
# Complete Integration
# ==========================================================


@pytest.mark.asyncio
async def test_loyalty_reward_service_complete_integration(
    db_session: AsyncSession,
    loyalty_reward_service: LoyaltyRewardService,
):
    """
    Complete integration test covering:

        Customer
            ↓
        LoyaltyAccount
            ↓
        LoyaltyReward
            ↓
        Eligibility
            ↓
        LoyaltyService
            ↓
        Point Ledger
            ↓
        LoyaltyRewardRedemption
            ↓
        Redemption History
    """

    # ======================================================
    # Customer
    # ======================================================

    user = await create_test_user(
        db_session,
    )

    print(
        f"Test customer created: {user.id}"
    )

    # ======================================================
    # Loyalty Account
    # ======================================================

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        points_balance=2000,
        lifetime_points=5000,
        tier=LoyaltyTier.GOLD,
    )

    print(
        "LoyaltyAccount creation: OK"
    )

    # ======================================================
    # Reward Catalogue
    # ======================================================

    free_parking = await create_test_reward(
        db_session,
        name="One Hour Free Parking",
        reward_type=LoyaltyRewardType.FREE_PARKING,
        points_cost=500,
        minimum_tier=LoyaltyTier.BRONZE,
    )

    coupon = await create_test_reward(
        db_session,
        name="KES 100 Parking Coupon",
        reward_type=LoyaltyRewardType.COUPON,
        points_cost=700,
        minimum_tier=LoyaltyTier.SILVER,
    )

    platinum_reward = await create_test_reward(
        db_session,
        name="VIP Platinum Benefit",
        reward_type=LoyaltyRewardType.VIP_BENEFIT,
        points_cost=1000,
        minimum_tier=LoyaltyTier.PLATINUM,
    )

    print(
        "Reward catalogue creation: OK"
    )

    # ======================================================
    # Eligibility
    # ======================================================

    eligible = (
        await loyalty_reward_service.get_eligible_rewards(
            customer_id=user.id,
        )
    )

    eligible_ids = {
        reward.id
        for reward in eligible
    }

    assert free_parking.id in eligible_ids
    assert coupon.id in eligible_ids
    assert platinum_reward.id not in eligible_ids

    print(
        "Reward eligibility query: OK"
    )

    # ======================================================
    # Reward Redemption
    # ======================================================

    (
        redemption,
        redeemed_reward,
        remaining_points,
        current_tier,
    ) = await loyalty_reward_service.redeem_reward(
        customer_id=user.id,
        reward_id=free_parking.id,
    )

    assert redemption.id is not None
    assert redeemed_reward.id == free_parking.id
    assert redemption.points_spent == 500
    assert remaining_points == 1500
    assert current_tier == LoyaltyTier.GOLD

    print(
        "Reward redemption: OK"
    )

    # ======================================================
    # Redemption Reference
    # ======================================================

    reference_result = (
        await loyalty_reward_service
        .get_redemption_by_reference(
            redemption.redemption_reference,
        )
    )

    assert reference_result.id == redemption.id

    print(
        "Redemption reference lookup: OK"
    )

    # ======================================================
    # Customer Redemption History
    # ======================================================

    history = (
        await loyalty_reward_service
        .get_customer_redemptions(
            customer_id=user.id,
        )
    )

    assert any(
        item.id == redemption.id
        for item in history
    )

    print(
        "Customer redemption history: OK"
    )

    # ======================================================
    # Reward Redemption History
    # ======================================================

    reward_history = (
        await loyalty_reward_service
        .get_reward_redemptions(
            reward_id=free_parking.id,
        )
    )

    assert any(
        item.id == redemption.id
        for item in reward_history
    )

    print(
        "Reward redemption history: OK"
    )

    # ======================================================
    # Counts
    # ======================================================

    customer_count = (
        await loyalty_reward_service
        .count_customer_redemptions(
            customer_id=user.id,
        )
    )

    reward_count = (
        await loyalty_reward_service
        .count_reward_redemptions(
            reward_id=free_parking.id,
        )
    )

    assert customer_count >= 1
    assert reward_count >= 1

    print(
        "Redemption counts: OK"
    )

    # ======================================================
    # Account Balance
    # ======================================================

    await db_session.refresh(
        account,
    )

    assert account.points_balance == 1500
    assert account.lifetime_points == 5000

    print(
        "Points balance after redemption: OK"
    )

    # ======================================================
    # Active Redemption
    # ======================================================

    active_redemption = (
        await loyalty_reward_service
        .get_active_redemption(
            redemption.id,
        )
    )

    assert active_redemption.id == redemption.id
    assert (
        active_redemption.status
        == RewardRedemptionStatus.REDEEMED
    )

    print(
        "Active redemption lookup: OK"
    )

    # ======================================================
    # Final Summary
    # ======================================================

    print()
    print(
        "===================================================="
    )
    print(
        "Loyalty Reward Service Integration Test"
    )
    print(
        "SERVICE -> REPOSITORY -> LOYALTY SERVICE -> POSTGRESQL"
    )
    print(
        "===================================================="
    )
    print(
        "INTEGRATION TEST: PASSED"
    )
    print(
        "===================================================="
    )