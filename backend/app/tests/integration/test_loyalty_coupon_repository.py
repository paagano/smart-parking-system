"""
Integration tests for LoyaltyCouponRepository.

These tests verify:

    PostgreSQL
        ↓
    LoyaltyAccount
        ↓
    LoyaltyReward
        ↓
    LoyaltyRewardRedemption
        ↓
    LoyaltyCoupon
        ↓
    LoyaltyCouponRepository

Business rules are intentionally NOT tested here.
Those belong in LoyaltyCouponService.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
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

from app.models.enums import (
    CouponStatus,
    CouponType,
    LoyaltyRewardStatus,
    LoyaltyRewardType,
    LoyaltyTier,
    RewardRedemptionStatus,
)

from app.models.loyalty_account import LoyaltyAccount
from app.models.loyalty_coupon import LoyaltyCoupon
from app.models.loyalty_reward import LoyaltyReward
from app.models.loyalty_reward_redemption import (
    LoyaltyRewardRedemption,
)
from app.models.user import User

from app.repositories.loyalty_coupon_repository import (
    LoyaltyCouponRepository,
)


# ==========================================================
# Test Database
# ==========================================================


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Create a real asynchronous PostgreSQL test database
    session using TEST_DATABASE_URL.
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
# Test Data Helpers
# ==========================================================


def unique_value(prefix: str) -> str:
    """
    Generate a unique value so repeated integration test
    executions do not collide with persisted test data.
    """

    return f"{prefix}-{uuid4().hex[:12].upper()}"


async def create_test_user(
    db: AsyncSession,
    *,
    email: str | None = None,
) -> User:
    """
    Create a minimal test customer.
    """

    if email is None:
        email = (
            f"coupon-test-{uuid4().hex[:12]}"
            "@example.com"
        )

    user = User(
        first_name="Coupon",
        last_name="Test",
        email=email,
        phone_number=None,
        password_hash="test-password-hash",
    )

    db.add(user)

    await db.flush()

    return user


async def create_test_loyalty_account(
    db: AsyncSession,
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
    name: str | None = None,
) -> LoyaltyReward:
    """
    Create a minimal loyalty reward.
    """

    if name is None:
        name = unique_value("Test-Coupon-Reward")

    now = datetime.now(timezone.utc).replace(
        tzinfo=None,
    )

    reward = LoyaltyReward(
        name=name,
        description="Test reward for coupon integration",
        reward_type=LoyaltyRewardType.FREE_PARKING,
        points_cost=500,
        monetary_value=Decimal("100.00"),
        status=LoyaltyRewardStatus.ACTIVE,
        is_active=True,
        minimum_tier=None,
        valid_from=now,
        valid_until=now + timedelta(days=30),
    )

    db.add(reward)

    await db.flush()

    return reward


async def create_test_redemption(
    db: AsyncSession,
    *,
    loyalty_account_id: int,
    reward_id: int,
    reference: str | None = None,
    points_spent: int = 500,
) -> LoyaltyRewardRedemption:
    """
    Create a reward redemption for coupon relationship tests.
    """

    if reference is None:
        reference = unique_value(
            "SP-REDEMPTION",
        )

    redemption = LoyaltyRewardRedemption(
        loyalty_account_id=loyalty_account_id,
        reward_id=reward_id,
        redemption_reference=reference,
        points_spent=points_spent,
        status=RewardRedemptionStatus.REDEEMED,
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


async def create_test_coupon(
    db: AsyncSession,
    *,
    loyalty_account_id: int,
    coupon_code: str | None = None,
    reward_redemption_id: int | None = None,
    coupon_type: CouponType = (
        CouponType.FIXED_AMOUNT_DISCOUNT
    ),
    value: Decimal | None = Decimal("100.00"),
    free_parking_minutes: int | None = None,
    status: CouponStatus = CouponStatus.ACTIVE,
    is_active: bool = True,
) -> LoyaltyCoupon:
    """
    Create a LoyaltyCoupon for repository integration tests.
    """

    if coupon_code is None:
        coupon_code = unique_value("SP-COUPON")

    now = datetime.now(timezone.utc)

    coupon = LoyaltyCoupon(
        loyalty_account_id=loyalty_account_id,
        reward_redemption_id=reward_redemption_id,
        coupon_code=coupon_code,
        coupon_type=coupon_type,
        value=value,
        free_parking_minutes=free_parking_minutes,
        status=status,
        is_active=is_active,
        valid_from=now,
        valid_until=now + timedelta(days=30),
        used_at=None,
        used_payment_transaction_id=None,
        description="Integration test coupon",
    )

    db.add(coupon)

    await db.flush()

    return coupon


# ==========================================================
# Create / Lookup
# ==========================================================


@pytest.mark.asyncio
async def test_create_and_get_coupon(
    db_session: AsyncSession,
):
    """
    Verify a coupon can be persisted and retrieved by ID.
    """

    repository = LoyaltyCouponRepository(
        db=db_session,
    )

    user = await create_test_user(db_session)

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    coupon_code = unique_value("SP-CREATE")

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_code=coupon_code,
    )

    await db_session.commit()

    result = await repository.get_by_id(
        coupon.id,
    )

    assert result is not None
    assert result.id == coupon.id
    assert result.loyalty_account_id == account.id
    assert result.coupon_code == coupon_code

    print("Create/Get coupon: OK")


@pytest.mark.asyncio
async def test_get_coupon_by_code(
    db_session: AsyncSession,
):
    """
    Verify coupon lookup by unique coupon code.
    """

    repository = LoyaltyCouponRepository(
        db=db_session,
    )

    user = await create_test_user(db_session)

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    coupon_code = unique_value("SP-CODE")

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_code=coupon_code,
    )

    await db_session.commit()

    result = await repository.get_by_code(
        coupon_code,
    )

    assert result is not None
    assert result.id == coupon.id
    assert result.coupon_code == coupon_code

    print("Get coupon by code: OK")


@pytest.mark.asyncio
async def test_coupon_exists_by_code(
    db_session: AsyncSession,
):
    """
    Verify coupon code existence lookup.
    """

    repository = LoyaltyCouponRepository(
        db=db_session,
    )

    user = await create_test_user(db_session)

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    coupon_code = unique_value("SP-EXISTS")

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_code=coupon_code,
    )

    await db_session.commit()

    exists = await repository.exists_by_code(
        coupon_code,
    )

    missing = await repository.exists_by_code(
        unique_value("SP-NOT-EXIST"),
    )

    assert exists is True
    assert missing is False

    print("Coupon existence check: OK")


# ==========================================================
# Customer Coupon Queries
# ==========================================================


@pytest.mark.asyncio
async def test_get_customer_coupon(
    db_session: AsyncSession,
):
    """
    Verify retrieval of a specific customer coupon.
    """

    repository = LoyaltyCouponRepository(
        db=db_session,
    )

    user = await create_test_user(db_session)

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
    )

    await db_session.commit()

    result = await repository.get_customer_coupon(
        loyalty_account_id=account.id,
        coupon_id=coupon.id,
    )

    assert result is not None
    assert result.id == coupon.id
    assert result.loyalty_account_id == account.id

    print("Get customer coupon: OK")


@pytest.mark.asyncio
async def test_get_customer_coupons(
    db_session: AsyncSession,
):
    """
    Verify customer coupon history.
    """

    repository = LoyaltyCouponRepository(
        db=db_session,
    )

    user = await create_test_user(db_session)

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    code_1 = unique_value("SP-HISTORY-001")
    code_2 = unique_value("SP-HISTORY-002")

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_code=code_1,
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_code=code_2,
    )

    await db_session.commit()

    results = await repository.get_customer_coupons(
        loyalty_account_id=account.id,
    )

    codes = {
        coupon.coupon_code
        for coupon in results
    }

    assert code_1 in codes
    assert code_2 in codes

    print("Get customer coupons: OK")


@pytest.mark.asyncio
async def test_get_active_customer_coupons(
    db_session: AsyncSession,
):
    """
    Verify only active customer coupons are returned.
    """

    repository = LoyaltyCouponRepository(
        db=db_session,
    )

    user = await create_test_user(db_session)

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    active_code = unique_value(
        "SP-ACTIVE",
    )

    used_code = unique_value(
        "SP-ACTIVE-USED",
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_code=active_code,
        status=CouponStatus.ACTIVE,
        is_active=True,
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_code=used_code,
        status=CouponStatus.USED,
        is_active=False,
    )

    await db_session.commit()

    results = await repository.get_active_customer_coupons(
        loyalty_account_id=account.id,
    )

    codes = {
        coupon.coupon_code
        for coupon in results
    }

    assert active_code in codes
    assert used_code not in codes

    assert all(
        coupon.status == CouponStatus.ACTIVE
        and coupon.is_active is True
        for coupon in results
    )

    print("Get active customer coupons: OK")


# ==========================================================
# Status / Type Filtering
# ==========================================================


@pytest.mark.asyncio
async def test_get_by_status(
    db_session: AsyncSession,
):
    """
    Verify coupons can be filtered by status.
    """

    repository = LoyaltyCouponRepository(
        db=db_session,
    )

    user = await create_test_user(db_session)

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    active_code = unique_value(
        "SP-STATUS-ACTIVE",
    )

    used_code = unique_value(
        "SP-STATUS-USED",
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_code=active_code,
        status=CouponStatus.ACTIVE,
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_code=used_code,
        status=CouponStatus.USED,
        is_active=False,
    )

    await db_session.commit()

    results = await repository.get_by_status(
        status=CouponStatus.ACTIVE,
    )

    assert all(
        coupon.status == CouponStatus.ACTIVE
        for coupon in results
    )

    codes = {
        coupon.coupon_code
        for coupon in results
    }

    assert active_code in codes

    print("Coupon status filtering: OK")


@pytest.mark.asyncio
async def test_get_customer_coupons_by_status(
    db_session: AsyncSession,
):
    """
    Verify customer coupons can be filtered by status.
    """

    repository = LoyaltyCouponRepository(
        db=db_session,
    )

    user = await create_test_user(db_session)

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    active_1 = unique_value(
        "SP-CS-ACTIVE-001",
    )

    active_2 = unique_value(
        "SP-CS-ACTIVE-002",
    )

    used = unique_value(
        "SP-CS-USED-001",
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_code=active_1,
        status=CouponStatus.ACTIVE,
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_code=active_2,
        status=CouponStatus.ACTIVE,
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_code=used,
        status=CouponStatus.USED,
        is_active=False,
    )

    await db_session.commit()

    results = await repository.get_customer_coupons_by_status(
        loyalty_account_id=account.id,
        status=CouponStatus.ACTIVE,
    )

    assert len(results) >= 2

    assert all(
        coupon.status == CouponStatus.ACTIVE
        for coupon in results
    )

    codes = {
        coupon.coupon_code
        for coupon in results
    }

    assert active_1 in codes
    assert active_2 in codes
    assert used not in codes

    print("Customer coupon status filtering: OK")


@pytest.mark.asyncio
async def test_get_by_type(
    db_session: AsyncSession,
):
    """
    Verify coupons can be filtered by coupon type.
    """

    repository = LoyaltyCouponRepository(
        db=db_session,
    )

    user = await create_test_user(db_session)

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    fixed_code = unique_value(
        "SP-TYPE-FIXED",
    )

    percent_code = unique_value(
        "SP-TYPE-PERCENT",
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_code=fixed_code,
        coupon_type=CouponType.FIXED_AMOUNT_DISCOUNT,
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_code=percent_code,
        coupon_type=CouponType.PERCENTAGE_DISCOUNT,
    )

    await db_session.commit()

    results = await repository.get_by_type(
        coupon_type=CouponType.FIXED_AMOUNT_DISCOUNT,
    )

    assert all(
        coupon.coupon_type
        == CouponType.FIXED_AMOUNT_DISCOUNT
        for coupon in results
    )

    codes = {
        coupon.coupon_code
        for coupon in results
    }

    assert fixed_code in codes

    print("Coupon type filtering: OK")


@pytest.mark.asyncio
async def test_get_customer_coupons_by_type(
    db_session: AsyncSession,
):
    """
    Verify customer coupons can be filtered by type.
    """

    repository = LoyaltyCouponRepository(
        db=db_session,
    )

    user = await create_test_user(db_session)

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    fixed_code = unique_value(
        "SP-CUSTOMER-TYPE-FIXED",
    )

    percent_code = unique_value(
        "SP-CUSTOMER-TYPE-PERCENT",
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_code=fixed_code,
        coupon_type=CouponType.FIXED_AMOUNT_DISCOUNT,
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_code=percent_code,
        coupon_type=CouponType.PERCENTAGE_DISCOUNT,
    )

    await db_session.commit()

    results = (
        await repository.get_customer_coupons_by_type(
            loyalty_account_id=account.id,
            coupon_type=CouponType.FIXED_AMOUNT_DISCOUNT,
        )
    )

    assert all(
        coupon.coupon_type
        == CouponType.FIXED_AMOUNT_DISCOUNT
        for coupon in results
    )

    codes = {
        coupon.coupon_code
        for coupon in results
    }

    assert fixed_code in codes

    print("Customer coupon type filtering: OK")


# ==========================================================
# Relationship Lookups
# ==========================================================


@pytest.mark.asyncio
async def test_get_by_reward_redemption(
    db_session: AsyncSession,
):
    """
    Verify coupon lookup by reward redemption.
    """

    repository = LoyaltyCouponRepository(
        db=db_session,
    )

    user = await create_test_user(db_session)

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    reward = await create_test_reward(
        db_session,
    )

    redemption = await create_test_redemption(
        db_session,
        loyalty_account_id=account.id,
        reward_id=reward.id,
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        reward_redemption_id=redemption.id,
    )

    await db_session.commit()

    result = await repository.get_by_reward_redemption(
        redemption.id,
    )

    assert result is not None
    assert result.id == coupon.id
    assert result.reward_redemption_id == redemption.id

    print("Reward redemption lookup: OK")


@pytest.mark.asyncio
async def test_get_by_payment_transaction_returns_none_when_unused(
    db_session: AsyncSession,
):
    """
    Verify an unused coupon is not associated with a
    payment transaction.
    """

    repository = LoyaltyCouponRepository(
        db=db_session,
    )

    user = await create_test_user(db_session)

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
    )

    await db_session.commit()

    result = await repository.get_by_payment_transaction(
        999999999,
    )

    assert result is None
    assert coupon.used_payment_transaction_id is None

    print(
        "Payment transaction lookup for unused coupon: OK",
    )


# ==========================================================
# General Queries / Counts
# ==========================================================


@pytest.mark.asyncio
async def test_get_all_coupons(
    db_session: AsyncSession,
):
    """
    Verify all-coupon retrieval with pagination.
    """

    repository = LoyaltyCouponRepository(
        db=db_session,
    )

    user = await create_test_user(db_session)

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    for _ in range(3):
        await create_test_coupon(
            db_session,
            loyalty_account_id=account.id,
        )

    await db_session.commit()

    results = await repository.get_all(
        limit=2,
        offset=0,
    )

    assert len(results) <= 2

    print("Get all coupons with pagination: OK")


@pytest.mark.asyncio
async def test_count_all_coupons(
    db_session: AsyncSession,
):
    """
    Verify total coupon count.
    """

    repository = LoyaltyCouponRepository(
        db=db_session,
    )

    user = await create_test_user(db_session)

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
    )

    await db_session.commit()

    count = await repository.count_all()

    assert count >= 2

    print("Count all coupons: OK")


@pytest.mark.asyncio
async def test_count_customer_coupons(
    db_session: AsyncSession,
):
    """
    Verify customer coupon count.
    """

    repository = LoyaltyCouponRepository(
        db=db_session,
    )

    user = await create_test_user(db_session)

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
    )

    await db_session.commit()

    count = await repository.count_customer_coupons(
        loyalty_account_id=account.id,
    )

    assert count >= 2

    print("Count customer coupons: OK")


@pytest.mark.asyncio
async def test_count_customer_coupons_by_status(
    db_session: AsyncSession,
):
    """
    Verify customer coupon counts can be filtered by status.
    """

    repository = LoyaltyCouponRepository(
        db=db_session,
    )

    user = await create_test_user(db_session)

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    active_1 = unique_value(
        "SP-COUNT-STATUS-ACTIVE-001",
    )

    active_2 = unique_value(
        "SP-COUNT-STATUS-ACTIVE-002",
    )

    used = unique_value(
        "SP-COUNT-STATUS-USED-001",
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_code=active_1,
        status=CouponStatus.ACTIVE,
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_code=active_2,
        status=CouponStatus.ACTIVE,
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_code=used,
        status=CouponStatus.USED,
        is_active=False,
    )

    await db_session.commit()

    count = (
        await repository.count_customer_coupons_by_status(
            loyalty_account_id=account.id,
            status=CouponStatus.ACTIVE,
        )
    )

    assert count >= 2

    print(
        "Count customer coupons by status: OK",
    )


# ==========================================================
# Update / Usage / Delete
# ==========================================================


@pytest.mark.asyncio
async def test_update_coupon(
    db_session: AsyncSession,
):
    """
    Verify a coupon can be updated and persisted.
    """

    repository = LoyaltyCouponRepository(
        db=db_session,
    )

    user = await create_test_user(db_session)

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        value=Decimal("100.00"),
    )

    await db_session.commit()

    coupon.value = Decimal("150.00")
    coupon.description = "Updated test coupon"

    updated = await repository.update(
        coupon,
    )

    await db_session.commit()

    result = await repository.get_by_id(
        coupon.id,
    )

    assert updated.id == coupon.id
    assert result is not None
    assert result.value == Decimal("150.00")
    assert result.description == "Updated test coupon"

    print("Coupon update: OK")


@pytest.mark.asyncio
async def test_mark_coupon_as_used(
    db_session: AsyncSession,
):
    """
    Verify a coupon can be persisted in its used state.
    """

    repository = LoyaltyCouponRepository(
        db=db_session,
    )

    user = await create_test_user(db_session)

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        status=CouponStatus.ACTIVE,
    )

    await db_session.commit()

    used_at = datetime.now(timezone.utc)

    coupon.status = CouponStatus.USED
    coupon.is_active = False
    coupon.used_at = used_at

    result = await repository.mark_as_used(
        coupon=coupon,
    )

    await db_session.commit()

    refreshed = await repository.get_by_id(
        coupon.id,
    )

    assert result.id == coupon.id
    assert refreshed is not None
    assert refreshed.status == CouponStatus.USED
    assert refreshed.is_active is False
    assert refreshed.used_at is not None

    print("Mark coupon as used: OK")


@pytest.mark.asyncio
async def test_delete_coupon(
    db_session: AsyncSession,
):
    """
    Verify a coupon can be deleted.
    """

    repository = LoyaltyCouponRepository(
        db=db_session,
    )

    user = await create_test_user(db_session)

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
    )

    await db_session.commit()

    coupon_id = coupon.id

    await repository.delete(
        coupon,
    )

    await db_session.commit()

    result = await repository.get_by_id(
        coupon_id,
    )

    assert result is None

    print("Coupon deletion: OK")


# ==========================================================
# Pagination
# ==========================================================


@pytest.mark.asyncio
async def test_coupon_pagination(
    db_session: AsyncSession,
):
    """
    Verify customer coupon pagination.
    """

    repository = LoyaltyCouponRepository(
        db=db_session,
    )

    user = await create_test_user(db_session)

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    for _ in range(5):
        await create_test_coupon(
            db_session,
            loyalty_account_id=account.id,
        )

    await db_session.commit()

    first_page = await repository.get_customer_coupons(
        loyalty_account_id=account.id,
        limit=2,
        offset=0,
    )

    second_page = await repository.get_customer_coupons(
        loyalty_account_id=account.id,
        limit=2,
        offset=2,
    )

    assert len(first_page) <= 2
    assert len(second_page) <= 2

    first_ids = {
        coupon.id
        for coupon in first_page
    }

    second_ids = {
        coupon.id
        for coupon in second_page
    }

    assert first_ids.isdisjoint(
        second_ids,
    )

    print("Coupon pagination: OK")


# ==========================================================
# Complete Integration
# ==========================================================


@pytest.mark.asyncio
async def test_loyalty_coupon_repository_complete_integration(
    db_session: AsyncSession,
):
    """
    Complete Loyalty Coupon Repository integration test.

    Workflow:

        User
          ↓
        LoyaltyAccount
          ↓
        LoyaltyReward
          ↓
        LoyaltyRewardRedemption
          ↓
        LoyaltyCoupon
          ↓
        Repository Queries
    """

    repository = LoyaltyCouponRepository(
        db=db_session,
    )

    # ======================================================
    # Customer
    # ======================================================

    user = await create_test_user(
        db_session,
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
    # Reward
    # ======================================================

    reward = await create_test_reward(
        db_session,
        name=unique_value(
            "Complete-Coupon-Reward",
        ),
    )

    print(
        "Reward catalogue creation: OK",
    )

    # ======================================================
    # Reward Redemption
    # ======================================================

    redemption = await create_test_redemption(
        db_session,
        loyalty_account_id=account.id,
        reward_id=reward.id,
    )

    print(
        "Reward redemption creation: OK",
    )

    # ======================================================
    # Coupon
    # ======================================================

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        reward_redemption_id=redemption.id,
        coupon_type=CouponType.FIXED_AMOUNT_DISCOUNT,
        value=Decimal("100.00"),
    )

    await db_session.commit()

    print(
        "Coupon creation: OK",
    )

    # ======================================================
    # Coupon Lookup
    # ======================================================

    by_id = await repository.get_by_id(
        coupon.id,
    )

    assert by_id is not None
    assert by_id.id == coupon.id

    print(
        "Coupon lookup: OK",
    )

    # ======================================================
    # Code Lookup
    # ======================================================

    by_code = await repository.get_by_code(
        coupon.coupon_code,
    )

    assert by_code is not None
    assert by_code.id == coupon.id

    print(
        "Coupon code lookup: OK",
    )

    # ======================================================
    # Existence
    # ======================================================

    exists = await repository.exists_by_code(
        coupon.coupon_code,
    )

    assert exists is True

    print(
        "Coupon existence check: OK",
    )

    # ======================================================
    # Customer Coupons
    # ======================================================

    customer_coupons = (
        await repository.get_customer_coupons(
            loyalty_account_id=account.id,
        )
    )

    assert any(
        item.id == coupon.id
        for item in customer_coupons
    )

    print(
        "Customer coupon history: OK",
    )

    # ======================================================
    # Active Coupons
    # ======================================================

    active_coupons = (
        await repository.get_active_customer_coupons(
            loyalty_account_id=account.id,
        )
    )

    assert any(
        item.id == coupon.id
        for item in active_coupons
    )

    print(
        "Active customer coupon retrieval: OK",
    )

    # ======================================================
    # Status Filter
    # ======================================================

    active_by_status = (
        await repository.get_customer_coupons_by_status(
            loyalty_account_id=account.id,
            status=CouponStatus.ACTIVE,
        )
    )

    assert any(
        item.id == coupon.id
        for item in active_by_status
    )

    print(
        "Coupon status filtering: OK",
    )

    # ======================================================
    # Type Filter
    # ======================================================

    fixed_coupons = (
        await repository.get_customer_coupons_by_type(
            loyalty_account_id=account.id,
            coupon_type=CouponType.FIXED_AMOUNT_DISCOUNT,
        )
    )

    assert any(
        item.id == coupon.id
        for item in fixed_coupons
    )

    print(
        "Coupon type filtering: OK",
    )

    # ======================================================
    # Reward Redemption Lookup
    # ======================================================

    by_redemption = (
        await repository.get_by_reward_redemption(
            redemption.id,
        )
    )

    assert by_redemption is not None
    assert by_redemption.id == coupon.id

    print(
        "Reward redemption lookup: OK",
    )

    # ======================================================
    # Counts
    # ======================================================

    customer_count = (
        await repository.count_customer_coupons(
            loyalty_account_id=account.id,
        )
    )

    assert customer_count >= 1

    active_count = (
        await repository.count_customer_coupons_by_status(
            loyalty_account_id=account.id,
            status=CouponStatus.ACTIVE,
        )
    )

    assert active_count >= 1

    print(
        "Coupon counts: OK",
    )

    # ======================================================
    # Update
    # ======================================================

    coupon.value = Decimal("125.00")

    await repository.update(
        coupon,
    )

    await db_session.commit()

    updated = await repository.get_by_id(
        coupon.id,
    )

    assert updated is not None
    assert updated.value == Decimal("125.00")

    print(
        "Coupon update: OK",
    )

    # ======================================================
    # Mark Used
    # ======================================================

    coupon.status = CouponStatus.USED
    coupon.is_active = False
    coupon.used_at = datetime.now(timezone.utc)

    await repository.mark_as_used(
        coupon=coupon,
    )

    await db_session.commit()

    used_coupon = await repository.get_by_id(
        coupon.id,
    )

    assert used_coupon is not None
    assert used_coupon.status == CouponStatus.USED
    assert used_coupon.is_active is False
    assert used_coupon.used_at is not None

    print(
        "Coupon usage lifecycle: OK",
    )

    # ======================================================
    # Final Verification
    # ======================================================

    final_coupon = await repository.get_by_code(
        coupon.coupon_code,
    )

    assert final_coupon is not None
    assert final_coupon.id == coupon.id
    assert final_coupon.status == CouponStatus.USED
    assert final_coupon.reward_redemption_id == (
        redemption.id
    )
    assert final_coupon.loyalty_account_id == (
        account.id
    )

    print(
        "Final coupon verification: OK",
    )

    print(
        "\n"
        "====================================================\n"
        "Loyalty Coupon Repository Integration Test\n"
        "POSTGRESQL -> LOYALTY ACCOUNT -> REWARD REDEMPTION\n"
        "-> COUPON REPOSITORY\n"
        "INTEGRATION TEST: PASSED\n"
        "===================================================="
    )