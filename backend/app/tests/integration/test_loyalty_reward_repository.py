"""
Integration tests for LoyaltyRewardRepository.

These tests verify:

    PostgreSQL
        ↓
    LoyaltyRewardRepository
        ↓
    LoyaltyReward
        ↓
    LoyaltyRewardRedemption

The tests use the configured test PostgreSQL database.

Business rules are intentionally NOT tested here.
Those belong to LoyaltyRewardService and LoyaltyService.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
import pytest_asyncio

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from collections.abc import AsyncGenerator
from app.config import settings

from app.models.enums import (
    LoyaltyRewardStatus,
    LoyaltyRewardType,
    LoyaltyTier,
    RewardRedemptionStatus,
)
from app.models.loyalty_account import LoyaltyAccount
from app.models.loyalty_reward import LoyaltyReward
from app.models.loyalty_reward_redemption import (
    LoyaltyRewardRedemption,
)
from app.models.user import User
from app.repositories.loyalty_reward_repository import (
    LoyaltyRewardRepository,
)

# ==========================================================
# Test Database
# ==========================================================


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Create a real asynchronous PostgreSQL test database
    session.

    Uses the configured TEST_DATABASE_URL so repository
    integration tests execute against the dedicated
    PostgreSQL test database.
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
# Helpers
# ==========================================================


async def create_test_user(
    db,
    *,
    email: str,
) -> User:
    """
    Create a minimal test user.
    """

    user = User(
        first_name="Loyalty",
        last_name="Test",
        email=email,
        phone_number=None,
        password_hash="test-password-hash",
    )

    db.add(user)

    await db.flush()

    return user


async def create_test_loyalty_account(
    db,
    *,
    customer_id: int,
) -> LoyaltyAccount:
    """
    Create a loyalty account for a test customer.
    """

    account = LoyaltyAccount(
        customer_id=customer_id,
        points_balance=5000,
        lifetime_points=5000,
        tier=LoyaltyTier.GOLD,
        is_active=True,
    )

    db.add(account)

    await db.flush()

    return account


async def create_test_reward(
    db: AsyncSession,
    *,
    name: str = "Test Reward",
    description: str = "Test reward",
    reward_type: LoyaltyRewardType = LoyaltyRewardType.FREE_PARKING,
    points_cost: int = 500,
    monetary_value: Decimal = Decimal("100.00"),
    status: LoyaltyRewardStatus = LoyaltyRewardStatus.ACTIVE,
    is_active: bool = True,
    minimum_tier: LoyaltyTier | None = None,
) -> LoyaltyReward:
    """
    Create and flush a LoyaltyReward for repository integration tests.

    valid_from and valid_until are stored as naive UTC datetimes because
    the loyalty_rewards database columns are TIMESTAMP WITHOUT TIME ZONE.
    """

    now = datetime.now(timezone.utc).replace(
        tzinfo=None,
    )

    reward = LoyaltyReward(
        name=name,
        description=description,
        reward_type=reward_type,
        points_cost=points_cost,
        monetary_value=monetary_value,
        status=status,
        is_active=is_active,
        minimum_tier=minimum_tier,
        valid_from=now,
        valid_until=now + timedelta(days=30),
    )

    db.add(reward)

    await db.flush()

    return reward


async def create_test_redemption(
    db,
    *,
    loyalty_account_id: int,
    reward_id: int,
    reference: str,
    points_spent: int = 500,
    status: RewardRedemptionStatus = (
        RewardRedemptionStatus.REDEEMED
    ),
) -> LoyaltyRewardRedemption:
    """
    Create a reward redemption directly in the test database.
    """

    redemption = LoyaltyRewardRedemption(
        loyalty_account_id=loyalty_account_id,
        reward_id=reward_id,
        redemption_reference=reference,
        points_spent=points_spent,
        status=status,
        used_at=None,
        expires_at=(
            datetime.now(timezone.utc)
            + timedelta(days=30)
        ),
        description="Integration test redemption",
    )

    db.add(redemption)

    await db.flush()

    return redemption


# ==========================================================
# Reward Catalogue Tests
# ==========================================================


@pytest.mark.asyncio
async def test_create_and_get_reward(
    db_session,
):
    """
    Verify a reward can be persisted and retrieved by ID.
    """

    repository = LoyaltyRewardRepository(
        db=db_session,
    )

    reward = await create_test_reward(
        db_session,
        name="One Hour Free Parking",
        reward_type=LoyaltyRewardType.FREE_PARKING,
        points_cost=500,
    )

    await db_session.commit()

    result = await repository.get_by_id(
        reward.id,
    )

    assert result is not None
    assert result.id == reward.id
    assert result.name == "One Hour Free Parking"
    assert result.reward_type == (
        LoyaltyRewardType.FREE_PARKING
    )
    assert result.points_cost == 500

    print(
        "Create/Get LoyaltyReward: OK",
    )


@pytest.mark.asyncio
async def test_get_active_reward(
    db_session,
):
    """
    Verify active rewards are returned by get_active_by_id().
    """

    repository = LoyaltyRewardRepository(
        db=db_session,
    )

    reward = await create_test_reward(
        db_session,
        name="KES 100 Discount",
        reward_type=LoyaltyRewardType.DISCOUNT,
        points_cost=700,
        status=LoyaltyRewardStatus.ACTIVE,
        is_active=True,
    )

    await db_session.commit()

    result = await repository.get_active_by_id(
        reward.id,
    )

    assert result is not None
    assert result.id == reward.id
    assert result.status == (
        LoyaltyRewardStatus.ACTIVE
    )
    assert result.is_active is True

    print(
        "Get active LoyaltyReward: OK",
    )


@pytest.mark.asyncio
async def test_inactive_reward_not_returned_as_active(
    db_session,
):
    """
    Verify inactive rewards are excluded from active lookup.
    """

    repository = LoyaltyRewardRepository(
        db=db_session,
    )

    reward = await create_test_reward(
        db_session,
        name="Inactive Reward",
        status=LoyaltyRewardStatus.INACTIVE,
        is_active=False,
    )

    await db_session.commit()

    result = await repository.get_active_by_id(
        reward.id,
    )

    assert result is None

    print(
        "Inactive LoyaltyReward correctly excluded: OK",
    )


@pytest.mark.asyncio
async def test_get_all_rewards(
    db_session,
):
    """
    Verify all rewards can be retrieved with pagination.
    """

    repository = LoyaltyRewardRepository(
        db=db_session,
    )

    await create_test_reward(
        db_session,
        name="Reward A",
        points_cost=100,
    )

    await create_test_reward(
        db_session,
        name="Reward B",
        points_cost=200,
    )

    await create_test_reward(
        db_session,
        name="Reward C",
        points_cost=300,
    )

    await db_session.commit()

    results = await repository.get_all(
        limit=100,
        offset=0,
    )

    assert len(results) >= 3

    names = {
        reward.name
        for reward in results
    }

    assert "Reward A" in names
    assert "Reward B" in names
    assert "Reward C" in names

    print(
        "Get all LoyaltyRewards with pagination: OK",
    )


@pytest.mark.asyncio
async def test_get_active_rewards(
    db_session,
):
    """
    Verify only active rewards are returned.
    """

    repository = LoyaltyRewardRepository(
        db=db_session,
    )

    await create_test_reward(
        db_session,
        name="Active Reward",
        status=LoyaltyRewardStatus.ACTIVE,
        is_active=True,
    )

    await create_test_reward(
        db_session,
        name="Inactive Reward",
        status=LoyaltyRewardStatus.INACTIVE,
        is_active=False,
    )

    await db_session.commit()

    results = await repository.get_active_rewards()

    names = {
        reward.name
        for reward in results
    }

    assert "Active Reward" in names
    assert "Inactive Reward" not in names

    for reward in results:
        assert reward.status == (
            LoyaltyRewardStatus.ACTIVE
        )
        assert reward.is_active is True

    print(
        "Get active LoyaltyRewards: OK",
    )


@pytest.mark.asyncio
async def test_get_rewards_by_type(
    db_session,
):
    """
    Verify rewards can be filtered by reward type.
    """

    repository = LoyaltyRewardRepository(
        db=db_session,
    )

    await create_test_reward(
        db_session,
        name="Free Parking",
        reward_type=LoyaltyRewardType.FREE_PARKING,
    )

    await create_test_reward(
        db_session,
        name="Discount",
        reward_type=LoyaltyRewardType.DISCOUNT,
    )

    await db_session.commit()

    results = await repository.get_by_type(
        LoyaltyRewardType.FREE_PARKING,
    )

    assert all(
        reward.reward_type
        == LoyaltyRewardType.FREE_PARKING
        for reward in results
    )

    names = {
        reward.name
        for reward in results
    }

    assert "Free Parking" in names

    print(
        "Filter LoyaltyRewards by type: OK",
    )


@pytest.mark.asyncio
async def test_get_active_rewards_by_type(
    db_session,
):
    """
    Verify active rewards can be filtered by type.
    """

    repository = LoyaltyRewardRepository(
        db=db_session,
    )

    await create_test_reward(
        db_session,
        name="Active Free Parking",
        reward_type=LoyaltyRewardType.FREE_PARKING,
        status=LoyaltyRewardStatus.ACTIVE,
        is_active=True,
    )

    await create_test_reward(
        db_session,
        name="Inactive Free Parking",
        reward_type=LoyaltyRewardType.FREE_PARKING,
        status=LoyaltyRewardStatus.INACTIVE,
        is_active=False,
    )

    await db_session.commit()

    results = await repository.get_active_by_type(
        LoyaltyRewardType.FREE_PARKING,
    )

    names = {
        reward.name
        for reward in results
    }

    assert "Active Free Parking" in names
    assert "Inactive Free Parking" not in names

    print(
        "Filter active LoyaltyRewards by type: OK",
    )


@pytest.mark.asyncio
async def test_get_eligible_rewards(
    db_session,
):
    """
    Verify rewards with no minimum tier are available
    and tier-specific rewards are returned when the
    supplied tier matches the configured minimum tier.

    The repository performs the direct database filter.
    Complex tier hierarchy rules belong to the service.
    """

    repository = LoyaltyRewardRepository(
        db=db_session,
    )

    universal_reward = await create_test_reward(
        db_session,
        name="Universal Reward",
        minimum_tier=None,
    )

    gold_reward = await create_test_reward(
        db_session,
        name="Gold Reward",
        minimum_tier=LoyaltyTier.GOLD,
    )

    await db_session.commit()

    results = await repository.get_eligible_rewards(
        LoyaltyTier.GOLD,
    )

    reward_ids = {
        reward.id
        for reward in results
    }

    assert universal_reward.id in reward_ids
    assert gold_reward.id in reward_ids

    print(
        "Get eligible LoyaltyRewards: OK",
    )


@pytest.mark.asyncio
async def test_count_rewards(
    db_session,
):
    """
    Verify reward count.
    """

    repository = LoyaltyRewardRepository(
        db=db_session,
    )

    await create_test_reward(
        db_session,
        name="Count Reward A",
    )

    await create_test_reward(
        db_session,
        name="Count Reward B",
    )

    await db_session.commit()

    count = await repository.count_rewards()

    assert count >= 2

    print(
        "Count LoyaltyRewards: OK",
    )


@pytest.mark.asyncio
async def test_count_active_rewards(
    db_session,
):
    """
    Verify active reward count.
    """

    repository = LoyaltyRewardRepository(
        db=db_session,
    )

    await create_test_reward(
        db_session,
        name="Count Active Reward",
        status=LoyaltyRewardStatus.ACTIVE,
        is_active=True,
    )

    await create_test_reward(
        db_session,
        name="Count Inactive Reward",
        status=LoyaltyRewardStatus.INACTIVE,
        is_active=False,
    )

    await db_session.commit()

    count = await repository.count_active_rewards()

    assert count >= 1

    print(
        "Count active LoyaltyRewards: OK",
    )


# ==========================================================
# Redemption Tests
# ==========================================================


@pytest.mark.asyncio
async def test_create_and_get_redemption(
    db_session,
):
    """
    Verify a reward redemption can be persisted and
    retrieved by ID.
    """

    repository = LoyaltyRewardRepository(
        db=db_session,
    )

    user = await create_test_user(
        db_session,
        email="reward-redemption-1@example.com",
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    reward = await create_test_reward(
        db_session,
        name="Redemption Test Reward",
        points_cost=500,
    )

    redemption = await create_test_redemption(
        db_session,
        loyalty_account_id=account.id,
        reward_id=reward.id,
        reference="LR-TEST-0001",
        points_spent=500,
    )

    await db_session.commit()

    result = await repository.get_redemption_by_id(
        redemption.id,
    )

    assert result is not None
    assert result.id == redemption.id
    assert result.loyalty_account_id == account.id
    assert result.reward_id == reward.id
    assert result.points_spent == 500
    assert result.status == (
        RewardRedemptionStatus.REDEEMED
    )

    print(
        "Create/Get LoyaltyRewardRedemption: OK",
    )


@pytest.mark.asyncio
async def test_get_redemption_by_reference(
    db_session,
):
    """
    Verify redemption lookup by unique reference.
    """

    repository = LoyaltyRewardRepository(
        db=db_session,
    )

    user = await create_test_user(
        db_session,
        email="reward-reference@example.com",
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    reward = await create_test_reward(
        db_session,
        name="Reference Reward",
    )

    redemption = await create_test_redemption(
        db_session,
        loyalty_account_id=account.id,
        reward_id=reward.id,
        reference="LR-TEST-REFERENCE-001",
    )

    await db_session.commit()

    result = await repository.get_redemption_by_reference(
        "LR-TEST-REFERENCE-001",
    )

    assert result is not None
    assert result.id == redemption.id
    assert result.redemption_reference == (
        "LR-TEST-REFERENCE-001"
    )

    print(
        "Get redemption by reference: OK",
    )


@pytest.mark.asyncio
async def test_redemption_exists(
    db_session,
):
    """
    Verify redemption reference existence check.
    """

    repository = LoyaltyRewardRepository(
        db=db_session,
    )

    user = await create_test_user(
        db_session,
        email="reward-exists@example.com",
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    reward = await create_test_reward(
        db_session,
        name="Exists Reward",
    )

    await create_test_redemption(
        db_session,
        loyalty_account_id=account.id,
        reward_id=reward.id,
        reference="LR-EXISTS-001",
    )

    await db_session.commit()

    exists = await repository.redemption_exists(
        "LR-EXISTS-001",
    )

    missing = await repository.redemption_exists(
        "LR-DOES-NOT-EXIST",
    )

    assert exists is True
    assert missing is False

    print(
        "Redemption existence check: OK",
    )


@pytest.mark.asyncio
async def test_get_customer_redemptions(
    db_session,
):
    """
    Verify redemption history for a loyalty account.
    """

    repository = LoyaltyRewardRepository(
        db=db_session,
    )

    user = await create_test_user(
        db_session,
        email="reward-history@example.com",
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    reward = await create_test_reward(
        db_session,
        name="History Reward",
    )

    await create_test_redemption(
        db_session,
        loyalty_account_id=account.id,
        reward_id=reward.id,
        reference="LR-HISTORY-001",
    )

    await create_test_redemption(
        db_session,
        loyalty_account_id=account.id,
        reward_id=reward.id,
        reference="LR-HISTORY-002",
    )

    await db_session.commit()

    results = await repository.get_customer_redemptions(
        account.id,
    )

    references = {
        redemption.redemption_reference
        for redemption in results
    }

    assert "LR-HISTORY-001" in references
    assert "LR-HISTORY-002" in references

    print(
        "Get customer reward redemption history: OK",
    )


@pytest.mark.asyncio
async def test_get_customer_redemptions_by_status(
    db_session,
):
    """
    Verify customer redemption history can be filtered
    by redemption status.
    """

    repository = LoyaltyRewardRepository(
        db=db_session,
    )

    user = await create_test_user(
        db_session,
        email="reward-status@example.com",
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    reward = await create_test_reward(
        db_session,
        name="Status Reward",
    )

    await create_test_redemption(
        db_session,
        loyalty_account_id=account.id,
        reward_id=reward.id,
        reference="LR-STATUS-REDEEMED",
        status=RewardRedemptionStatus.REDEEMED,
    )

    await create_test_redemption(
        db_session,
        loyalty_account_id=account.id,
        reward_id=reward.id,
        reference="LR-STATUS-CANCELLED",
        status=RewardRedemptionStatus.CANCELLED,
    )

    await db_session.commit()

    results = (
        await repository.get_customer_redemptions_by_status(
            account.id,
            RewardRedemptionStatus.REDEEMED,
        )
    )

    assert len(results) >= 1

    assert all(
        redemption.status
        == RewardRedemptionStatus.REDEEMED
        for redemption in results
    )

    references = {
        redemption.redemption_reference
        for redemption in results
    }

    assert "LR-STATUS-REDEEMED" in references
    assert "LR-STATUS-CANCELLED" not in references

    print(
        "Filter customer redemptions by status: OK",
    )


@pytest.mark.asyncio
async def test_get_redemptions_for_reward(
    db_session,
):
    """
    Verify redemption history for a specific reward.
    """

    repository = LoyaltyRewardRepository(
        db=db_session,
    )

    user = await create_test_user(
        db_session,
        email="reward-specific-history@example.com",
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    reward_a = await create_test_reward(
        db_session,
        name="Reward A History",
    )

    reward_b = await create_test_reward(
        db_session,
        name="Reward B History",
    )

    await create_test_redemption(
        db_session,
        loyalty_account_id=account.id,
        reward_id=reward_a.id,
        reference="LR-REWARD-A-001",
    )

    await create_test_redemption(
        db_session,
        loyalty_account_id=account.id,
        reward_id=reward_b.id,
        reference="LR-REWARD-B-001",
    )

    await db_session.commit()

    results = await repository.get_redemptions_for_reward(
        reward_a.id,
    )

    assert len(results) >= 1

    assert all(
        redemption.reward_id == reward_a.id
        for redemption in results
    )

    references = {
        redemption.redemption_reference
        for redemption in results
    }

    assert "LR-REWARD-A-001" in references
    assert "LR-REWARD-B-001" not in references

    print(
        "Get redemptions for specific reward: OK",
    )


@pytest.mark.asyncio
async def test_count_customer_redemptions(
    db_session,
):
    """
    Verify customer redemption count.
    """

    repository = LoyaltyRewardRepository(
        db=db_session,
    )

    user = await create_test_user(
        db_session,
        email="reward-count-customer@example.com",
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    reward = await create_test_reward(
        db_session,
        name="Customer Count Reward",
    )

    await create_test_redemption(
        db_session,
        loyalty_account_id=account.id,
        reward_id=reward.id,
        reference="LR-COUNT-CUSTOMER-001",
    )

    await create_test_redemption(
        db_session,
        loyalty_account_id=account.id,
        reward_id=reward.id,
        reference="LR-COUNT-CUSTOMER-002",
    )

    await db_session.commit()

    count = await repository.count_customer_redemptions(
        account.id,
    )

    assert count >= 2

    print(
        "Count customer redemptions: OK",
    )


@pytest.mark.asyncio
async def test_count_redemptions_for_reward(
    db_session,
):
    """
    Verify redemption count for a specific reward.
    """

    repository = LoyaltyRewardRepository(
        db=db_session,
    )

    user = await create_test_user(
        db_session,
        email="reward-count-specific@example.com",
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    reward_a = await create_test_reward(
        db_session,
        name="Reward Count A",
    )

    reward_b = await create_test_reward(
        db_session,
        name="Reward Count B",
    )

    await create_test_redemption(
        db_session,
        loyalty_account_id=account.id,
        reward_id=reward_a.id,
        reference="LR-COUNT-A-001",
    )

    await create_test_redemption(
        db_session,
        loyalty_account_id=account.id,
        reward_id=reward_a.id,
        reference="LR-COUNT-A-002",
    )

    await create_test_redemption(
        db_session,
        loyalty_account_id=account.id,
        reward_id=reward_b.id,
        reference="LR-COUNT-B-001",
    )

    await db_session.commit()

    count = await repository.count_redemptions_for_reward(
        reward_a.id,
    )

    assert count >= 2

    print(
        "Count redemptions for reward: OK",
    )


@pytest.mark.asyncio
async def test_get_active_redemption(
    db_session,
):
    """
    Verify an active/redeemed redemption can be retrieved.
    """

    repository = LoyaltyRewardRepository(
        db=db_session,
    )

    user = await create_test_user(
        db_session,
        email="reward-active-redemption@example.com",
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    reward = await create_test_reward(
        db_session,
        name="Active Redemption Reward",
    )

    redemption = await create_test_redemption(
        db_session,
        loyalty_account_id=account.id,
        reward_id=reward.id,
        reference="LR-ACTIVE-001",
        status=RewardRedemptionStatus.REDEEMED,
    )

    await db_session.commit()

    result = await repository.get_active_redemption(
        redemption.id,
    )

    assert result is not None
    assert result.id == redemption.id
    assert result.status == (
        RewardRedemptionStatus.REDEEMED
    )

    print(
        "Get active reward redemption: OK",
    )


# ==========================================================
# Pagination Tests
# ==========================================================


@pytest.mark.asyncio
async def test_reward_pagination(
    db_session,
):
    """
    Verify reward pagination.
    """

    repository = LoyaltyRewardRepository(
        db=db_session,
    )

    await create_test_reward(
        db_session,
        name="Pagination Reward A",
    )

    await create_test_reward(
        db_session,
        name="Pagination Reward B",
    )

    await create_test_reward(
        db_session,
        name="Pagination Reward C",
    )

    await db_session.commit()

    first_page = await repository.get_all(
        limit=2,
        offset=0,
    )

    second_page = await repository.get_all(
        limit=2,
        offset=2,
    )

    assert len(first_page) <= 2
    assert len(second_page) <= 2

    first_ids = {
        reward.id
        for reward in first_page
    }

    second_ids = {
        reward.id
        for reward in second_page
    }

    assert first_ids.isdisjoint(
        second_ids,
    )

    print(
        "Reward pagination: OK",
    )


@pytest.mark.asyncio
async def test_redemption_pagination(
    db_session,
):
    """
    Verify customer redemption pagination.
    """

    repository = LoyaltyRewardRepository(
        db=db_session,
    )

    user = await create_test_user(
        db_session,
        email="reward-pagination@example.com",
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    reward = await create_test_reward(
        db_session,
        name="Redemption Pagination Reward",
    )

    for index in range(1, 4):
        await create_test_redemption(
            db_session,
            loyalty_account_id=account.id,
            reward_id=reward.id,
            reference=f"LR-PAGE-{index:03d}",
        )

    await db_session.commit()

    first_page = (
        await repository.get_customer_redemptions(
            account.id,
            limit=2,
            offset=0,
        )
    )

    second_page = (
        await repository.get_customer_redemptions(
            account.id,
            limit=2,
            offset=2,
        )
    )

    assert len(first_page) <= 2
    assert len(second_page) <= 2

    first_ids = {
        redemption.id
        for redemption in first_page
    }

    second_ids = {
        redemption.id
        for redemption in second_page
    }

    assert first_ids.isdisjoint(
        second_ids,
    )

    print(
        "Redemption pagination: OK",
    )


# ==========================================================
# Complete Integration Test
# ==========================================================


@pytest.mark.asyncio
async def test_loyalty_reward_repository_complete_integration(
    db_session,
):
    """
    Complete integration test covering:

        Customer
            ↓
        LoyaltyAccount
            ↓
        LoyaltyReward
            ↓
        LoyaltyRewardRedemption
            ↓
        Repository queries
    """

    repository = LoyaltyRewardRepository(
        db=db_session,
    )

    # ======================================================
    # Customer
    # ======================================================

    user = await create_test_user(
        db_session,
        email="loyalty-reward-complete@example.com",
    )

    print(
        f"Test customer created: {user.id}",
    )

    # ======================================================
    # Loyalty Account
    # ======================================================

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    print(
        "LoyaltyAccount creation: OK",
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

    discount = await create_test_reward(
        db_session,
        name="KES 250 Discount",
        reward_type=LoyaltyRewardType.DISCOUNT,
        points_cost=1500,
        minimum_tier=LoyaltyTier.GOLD,
    )

    print(
        "Reward catalogue creation: OK",
    )

    # ======================================================
    # Reward Retrieval
    # ======================================================

    retrieved_reward = await repository.get_by_id(
        free_parking.id,
    )

    assert retrieved_reward is not None
    assert retrieved_reward.id == free_parking.id

    print(
        "Reward lookup: OK",
    )

    # ======================================================
    # Active Rewards
    # ======================================================

    active_rewards = (
        await repository.get_active_rewards()
    )

    assert any(
        reward.id == free_parking.id
        for reward in active_rewards
    )

    print(
        "Active reward retrieval: OK",
    )

    # ======================================================
    # Reward Type Filtering
    # ======================================================

    free_parking_rewards = (
        await repository.get_active_by_type(
            LoyaltyRewardType.FREE_PARKING,
        )
    )

    assert any(
        reward.id == free_parking.id
        for reward in free_parking_rewards
    )

    print(
        "Reward type filtering: OK",
    )

    # ======================================================
    # Tier Eligibility
    # ======================================================

    eligible_rewards = (
        await repository.get_eligible_rewards(
            LoyaltyTier.GOLD,
        )
    )

    eligible_ids = {
        reward.id
        for reward in eligible_rewards
    }

    assert free_parking.id in eligible_ids
    assert discount.id in eligible_ids

    # Note:
    # The repository intentionally performs direct
    # minimum_tier matching. Hierarchical tier evaluation
    # belongs to the service layer.

    print(
        "Reward eligibility query: OK",
    )

    # ======================================================
    # Redemption
    # ======================================================

    redemption = await create_test_redemption(
        db_session,
        loyalty_account_id=account.id,
        reward_id=free_parking.id,
        reference="LR-COMPLETE-001",
        points_spent=free_parking.points_cost,
    )

    await db_session.commit()

    print(
        "Reward redemption creation: OK",
    )

    # ======================================================
    # Redemption Lookup
    # ======================================================

    retrieved_redemption = (
        await repository.get_redemption_by_id(
            redemption.id,
        )
    )

    assert retrieved_redemption is not None
    assert retrieved_redemption.id == redemption.id
    assert retrieved_redemption.reward_id == (
        free_parking.id
    )
    assert retrieved_redemption.loyalty_account_id == (
        account.id
    )

    print(
        "Redemption lookup: OK",
    )

    # ======================================================
    # Reference Lookup
    # ======================================================

    reference_result = (
        await repository.get_redemption_by_reference(
            "LR-COMPLETE-001",
        )
    )

    assert reference_result is not None
    assert reference_result.id == redemption.id

    print(
        "Redemption reference lookup: OK",
    )

    # ======================================================
    # Customer History
    # ======================================================

    customer_history = (
        await repository.get_customer_redemptions(
            account.id,
        )
    )

    assert any(
        item.id == redemption.id
        for item in customer_history
    )

    print(
        "Customer redemption history: OK",
    )

    # ======================================================
    # Reward History
    # ======================================================

    reward_history = (
        await repository.get_redemptions_for_reward(
            free_parking.id,
        )
    )

    assert any(
        item.id == redemption.id
        for item in reward_history
    )

    print(
        "Reward redemption history: OK",
    )

    # ======================================================
    # Counts
    # ======================================================

    customer_count = (
        await repository.count_customer_redemptions(
            account.id,
        )
    )

    reward_count = (
        await repository.count_redemptions_for_reward(
            free_parking.id,
        )
    )

    assert customer_count >= 1
    assert reward_count >= 1

    print(
        "Redemption counts: OK",
    )

    # ======================================================
    # Existence
    # ======================================================

    assert (
        await repository.redemption_exists(
            "LR-COMPLETE-001",
        )
        is True
    )

    assert (
        await repository.redemption_exists(
            "LR-COMPLETE-MISSING",
        )
        is False
    )

    print(
        "Redemption existence check: OK",
    )

    # ======================================================
    # Final
    # ======================================================

    print()
    print("=" * 52)
    print(
        "Loyalty Reward Repository Integration Test",
    )
    print(
        "POSTGRESQL -> REWARD CATALOGUE -> REDEMPTION",
    )
    print(
        "INTEGRATION TEST: PASSED",
    )
    print("=" * 52)