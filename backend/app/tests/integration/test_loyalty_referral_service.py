"""
Loyalty Referral Service Integration Tests.

Tests the LoyaltyReferralService business rules against the
real PostgreSQL test database.

Architecture under test
-----------------------

    Test
      |
      v
LoyaltyReferralService
      |
      +--------------------------+
      |                          |
      v                          v
LoyaltyReferralRepository    LoyaltyService
      |                          |
      v                          v
PostgreSQL                  LoyaltyRepository
                                 |
                                 v
                             PostgreSQL


These tests intentionally do NOT involve:

- FastAPI
- API routers
- Authentication dependencies
- NotificationService
- PaymentService
- HTTP requests

The purpose of this suite is to verify the referral service
business rules and the integration between:

    LoyaltyReferralService
        +
    LoyaltyReferralRepository
        +
    LoyaltyService
        +
    LoyaltyRepository
        +
    PostgreSQL
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio

from sqlalchemy import select
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
    ReferralStatus,
    UserRole,
)

from app.models.loyalty_account import (
    LoyaltyAccount,
)

from app.models.loyalty_point_transaction import (
    LoyaltyPointTransaction,
)

from app.models.loyalty_referral import (
    LoyaltyReferral,
)

from app.models.user import (
    User,
)

from app.repositories.loyalty_referral_repository import (
    LoyaltyReferralRepository,
)

from app.repositories.loyalty_repository import (
    LoyaltyRepository,
)

from app.services.loyalty_referral_service import (
    LoyaltyReferralService,
)

from app.services.loyalty_service import (
    LoyaltyService,
)


# ==========================================================
# Test Database
# ==========================================================


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[
    AsyncSession,
    None,
]:
    """
    Create a real asynchronous PostgreSQL test database
    session.

    Uses TEST_DATABASE_URL so these tests run against the
    dedicated PostgreSQL test database.
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
async def loyalty_referral_service(
    db_session: AsyncSession,
) -> LoyaltyReferralService:
    """
    Create a real LoyaltyReferralService backed by:

        LoyaltyReferralRepository
                +
        LoyaltyService
                +
        LoyaltyRepository
                +
        PostgreSQL
    """

    referral_repository = LoyaltyReferralRepository(
        db=db_session,
    )

    loyalty_repository = LoyaltyRepository(
        db=db_session,
    )

    loyalty_service = LoyaltyService(
        db=db_session,
        repository=loyalty_repository,
    )

    return LoyaltyReferralService(
        db=db_session,
        repository=referral_repository,
        loyalty_service=loyalty_service,
    )


# ==========================================================
# Test User Factory
# ==========================================================

async def create_test_user(
    db: AsyncSession,
    *,
    prefix: str = "referral",
    is_active: bool = True,
) -> User:
    """
    Create a unique real test customer.
    """

    unique_id = uuid4().hex[:10].lower()

    user = User(
        first_name="Referral",
        last_name="Service Test",
        email=(
            f"{prefix}.{unique_id}"
            "@test.local"
        ),
        phone_number=(
            f"0712{unique_id[:6]}"
        ),
        password_hash=(
            "integration-test-password-hash"
        ),
        role=UserRole.DRIVER,
        is_active=is_active,
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
    Create a real loyalty account for testing.
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
# Customer + Loyalty Account Factory
# ==========================================================


async def create_customer_with_account(
    db: AsyncSession,
    *,
    prefix: str = "referral",
    points_balance: int = 0,
    lifetime_points: int = 0,
    tier: LoyaltyTier = LoyaltyTier.BRONZE,
    is_active: bool = True,
) -> tuple[User, LoyaltyAccount]:
    """
    Create a real customer and loyalty account.
    """

    user = await create_test_user(
        db,
        prefix=prefix,
        is_active=is_active,
    )

    account = await create_test_loyalty_account(
        db,
        customer_id=user.id,
        points_balance=points_balance,
        lifetime_points=lifetime_points,
        tier=tier,
        is_active=is_active,
    )

    return user, account


# ==========================================================
# Referral Factory
# ==========================================================


async def create_test_referral(
    db: AsyncSession,
    *,
    referrer_id: int,
    referred_id: int,
    referral_code: str | None = None,
    status: ReferralStatus = ReferralStatus.PENDING,
    reward_points: int = 100,
    notes: str = "Referral service integration test",
) -> LoyaltyReferral:
    """
    Create and persist a real LoyaltyReferral.

    This helper deliberately creates the referral directly
    through the database session so individual service
    behaviours can be tested independently.
    """

    if referral_code is None:
        referral_code = (
            "REF-"
            f"{uuid4().hex[:12].upper()}"
        )

    referral = LoyaltyReferral(
        referrer_id=referrer_id,
        referred_id=referred_id,
        referral_code=referral_code,
        status=status,
        reward_points=reward_points,
        notes=notes,
    )

    db.add(referral)

    await db.flush()
    await db.refresh(referral)

    return referral


# ==========================================================
# Creation Tests
# ==========================================================


@pytest.mark.asyncio
async def test_create_referral(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Verify that the service creates a valid referral.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    referral = (
        await loyalty_referral_service.create_referral(
            referrer_id=referrer.id,
            referred_id=referred.id,
            referral_code=f"REF-SERVICE-{uuid4().hex[:12].upper()}",
            reward_points=100,
            notes="Service integration test",
        )
    )

    assert referral is not None
    assert referral.id is not None
    assert referral.referrer_id == referrer.id
    assert referral.referred_id == referred.id
    assert referral.referral_code.startswith("REF-SERVICE-")
    assert referral.status == ReferralStatus.PENDING
    assert referral.reward_points == 100
    assert referral.notes == "Service integration test"

    print(
        "Create referral through service: OK"
    )


# ==========================================================
# Referral Code Normalisation
# ==========================================================


@pytest.mark.asyncio
async def test_create_referral_normalises_code(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Verify referral codes are stripped and converted to
    uppercase.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    referral = (
        await loyalty_referral_service.create_referral(
            referrer_id=referrer.id,
            referred_id=referred.id,
            referral_code=f"  ref-service-{uuid4().hex[:12]}  ",
        )
    )

    assert referral.referral_code.startswith("REF-SERVICE-")

    print(
        "Referral code normalisation: OK"
    )


# ==========================================================
# Creation Validation
# ==========================================================


@pytest.mark.asyncio
async def test_create_referral_rejects_self_referral(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    A customer cannot refer themselves.
    """

    customer, _ = await create_customer_with_account(
        db_session,
        prefix="self-referral",
    )

    with pytest.raises(
        BadRequestException,
        match="cannot refer themselves",
    ):
        await loyalty_referral_service.create_referral(
            referrer_id=customer.id,
            referred_id=customer.id,
            referral_code="REF-SELF-001",
        )

    print(
        "Self-referral correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_create_referral_rejects_empty_code(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Referral code is mandatory.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    with pytest.raises(
        BadRequestException,
        match="Referral code is required",
    ):
        await loyalty_referral_service.create_referral(
            referrer_id=referrer.id,
            referred_id=referred.id,
            referral_code="   ",
        )

    print(
        "Empty referral code correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_create_referral_rejects_negative_reward(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Referral reward points cannot be negative.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    with pytest.raises(
        BadRequestException,
        match="cannot be negative",
    ):
        await loyalty_referral_service.create_referral(
            referrer_id=referrer.id,
            referred_id=referred.id,
            referral_code="REF-NEGATIVE-001",
            reward_points=-10,
        )

    print(
        "Negative referral reward correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_create_referral_rejects_missing_referrer(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Referrer must exist.
    """

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    with pytest.raises(
        NotFoundException,
        match="Referrer customer not found",
    ):
        await loyalty_referral_service.create_referral(
            referrer_id=999999999,
            referred_id=referred.id,
            referral_code="REF-MISSING-REFERRER",
        )

    print(
        "Missing referrer correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_create_referral_rejects_missing_referred_customer(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Referred customer must exist.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    with pytest.raises(
        NotFoundException,
        match="Referred customer not found",
    ):
        await loyalty_referral_service.create_referral(
            referrer_id=referrer.id,
            referred_id=999999999,
            referral_code="REF-MISSING-CUSTOMER",
        )

    print(
        "Missing referred customer correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_create_referral_rejects_inactive_referrer(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    An inactive referrer cannot create a referral.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="inactive-referrer",
        is_active=False,
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    with pytest.raises(
        BadRequestException,
        match="Referrer customer is inactive",
    ):
        await loyalty_referral_service.create_referral(
            referrer_id=referrer.id,
            referred_id=referred.id,
            referral_code=f"REF-INACTIVE-REFERRER-{uuid4().hex[:12].upper()}",
        )

    print(
        "Inactive referrer correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_create_referral_rejects_inactive_referred_customer(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    An inactive referred customer cannot participate in
    a referral.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="inactive-referred",
        is_active=False,
    )

    with pytest.raises(
        BadRequestException,
        match="Referred customer is inactive",
    ):
        await loyalty_referral_service.create_referral(
            referrer_id=referrer.id,
            referred_id=referred.id,
            referral_code=f"REF-INACTIVE-REFERRED-{uuid4().hex[:12].upper()}",
        )

    print(
        "Inactive referred customer correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_create_referral_rejects_duplicate_code(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Referral codes must be unique.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    referred_one, _ = (
        await create_customer_with_account(
            db_session,
            prefix="referred-one",
        )
    )

    referred_two, _ = (
        await create_customer_with_account(
            db_session,
            prefix="referred-two",
        )
    )

    referral_code = (
        f"REF-DUPLICATE-{uuid4().hex[:12].upper()}"
    )

    await loyalty_referral_service.create_referral(
        referrer_id=referrer.id,
        referred_id=referred_one.id,
        referral_code=referral_code,
    )

    with pytest.raises(
        BadRequestException,
        match="Referral code already exists",
    ):
        await loyalty_referral_service.create_referral(
            referrer_id=referrer.id,
            referred_id=referred_two.id,
            referral_code=referral_code,
        )

    print(
        "Duplicate referral code correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_create_referral_rejects_existing_pending_referral(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    A referred customer cannot have multiple pending
    referrals.
    """

    referrer_one, _ = (
        await create_customer_with_account(
            db_session,
            prefix="referrer-one",
        )
    )

    referrer_two, _ = (
        await create_customer_with_account(
            db_session,
            prefix="referrer-two",
        )
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    first_referral_code = (
        f"REF-PENDING-{uuid4().hex[:12].upper()}"
    )
    second_referral_code = (
        f"REF-PENDING-{uuid4().hex[:12].upper()}"
    )

    await loyalty_referral_service.create_referral(
        referrer_id=referrer_one.id,
        referred_id=referred.id,
        referral_code=first_referral_code,
    )

    with pytest.raises(
        BadRequestException,
        match="already has a pending referral",
    ):
        await loyalty_referral_service.create_referral(
            referrer_id=referrer_two.id,
            referred_id=referred.id,
            referral_code=second_referral_code,
        )

    print(
        "Duplicate pending referral correctly rejected: OK"
    )


# ==========================================================
# Retrieval Tests
# ==========================================================


@pytest.mark.asyncio
async def test_get_referral(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Verify referral retrieval by ID.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    created = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
    )

    found = (
        await loyalty_referral_service.get_referral(
            created.id,
        )
    )

    assert found is not None
    assert found.id == created.id
    assert found.referrer_id == referrer.id
    assert found.referred_id == referred.id

    print(
        "Get referral through service: OK"
    )


@pytest.mark.asyncio
async def test_get_referral_not_found(
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Missing referral IDs must raise NotFoundException.
    """

    with pytest.raises(
        NotFoundException,
        match="Loyalty referral not found",
    ):
        await loyalty_referral_service.get_referral(
            999999999,
        )

    print(
        "Missing referral correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_get_referral_by_code(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Verify referral lookup by code.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    created = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
        referral_code="REF-LOOKUP-001",
    )

    found = (
        await loyalty_referral_service
        .get_referral_by_code(
            " ref-lookup-001 ",
        )
    )

    assert found is not None
    assert found.id == created.id
    assert found.referral_code == (
        "REF-LOOKUP-001"
    )

    print(
        "Referral code lookup through service: OK"
    )


# ==========================================================
# Referral Code Validation
# ==========================================================


@pytest.mark.asyncio
async def test_validate_referral_code_success(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    A valid referral code should validate successfully.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    referral_code = (
        f"REF-VALIDATE-{uuid4().hex[:12].upper()}"
    )

    referral = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
        referral_code=referral_code,
    )

    result = (
        await loyalty_referral_service
        .validate_referral_code(
            customer_id=referred.id,
            referral_code=referral_code,
        )
    )

    found, valid, exists, active, reason = result

    assert found is not None
    assert found.id == referral.id
    assert valid is True
    assert exists is True
    assert active is True
    assert reason is None

    print(
        "Valid referral code accepted: OK"
    )


@pytest.mark.asyncio
async def test_validate_referral_code_not_found(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    A non-existent referral code must be rejected.
    """

    customer, _ = await create_customer_with_account(
        db_session,
        prefix="customer",
    )

    result = (
        await loyalty_referral_service
        .validate_referral_code(
            customer_id=customer.id,
            referral_code="REF-DOES-NOT-EXIST",
        )
    )

    referral, valid, exists, active, reason = result

    assert referral is None
    assert valid is False
    assert exists is False
    assert active is False
    assert reason == (
        "Referral code does not exist."
    )

    print(
        "Non-existent referral code rejected: OK"
    )


@pytest.mark.asyncio
async def test_validate_referral_code_rejects_self_referral(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    A referrer cannot use their own referral code.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    referral = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
        referral_code="REF-SELF-VALIDATE",
    )

    result = (
        await loyalty_referral_service
        .validate_referral_code(
            customer_id=referrer.id,
            referral_code=referral.referral_code,
        )
    )

    found, valid, exists, active, reason = result

    assert found is not None
    assert found.id == referral.id
    assert valid is False
    assert exists is True
    assert active is True
    assert reason == (
        "A customer cannot use their own referral code."
    )

    print(
        "Self-referral code usage correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_validate_referral_code_rejects_non_pending_referral(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    A referral that is no longer PENDING cannot be used.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    referral = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
        referral_code="REF-QUALIFIED-CODE",
        status=ReferralStatus.QUALIFIED,
    )

    result = (
        await loyalty_referral_service
        .validate_referral_code(
            customer_id=referred.id,
            referral_code=referral.referral_code,
        )
    )

    found, valid, exists, active, reason = result

    assert found is not None
    assert valid is False
    assert exists is True
    assert active is False
    assert reason == (
        "Referral is no longer active."
    )

    print(
        "Non-pending referral code correctly rejected: OK"
    )


# ==========================================================
# Qualification
# ==========================================================


@pytest.mark.asyncio
async def test_qualify_referral(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Verify PENDING → QUALIFIED.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    referral = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
    )

    qualified = (
        await loyalty_referral_service.qualify_referral(
            referral_id=referral.id,
        )
    )

    assert qualified.status == (
        ReferralStatus.QUALIFIED
    )

    assert qualified.qualified_at is not None

    print(
        "Referral qualification PENDING -> QUALIFIED: OK"
    )


@pytest.mark.asyncio
async def test_qualify_referral_rejects_non_pending(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Only PENDING referrals may be qualified.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    referral = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
        status=ReferralStatus.QUALIFIED,
    )

    with pytest.raises(
        BadRequestException,
        match="Only pending referrals can be qualified",
    ):
        await loyalty_referral_service.qualify_referral(
            referral_id=referral.id,
        )

    print(
        "Invalid qualification transition correctly rejected: OK"
    )


# ==========================================================
# Reward Integration
# ==========================================================


@pytest.mark.asyncio
async def test_reward_referral_awards_loyalty_points(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Critical integration test.

    Verify:

        QUALIFIED referral
            ->
        LoyaltyService.award_points()
            ->
        LoyaltyAccount updated
            ->
        LoyaltyPointTransaction created
            ->
        Referral becomes REWARDED.
    """

    referrer, referrer_account = (
        await create_customer_with_account(
            db_session,
            prefix="reward-referrer",
            points_balance=0,
            lifetime_points=0,
            tier=LoyaltyTier.BRONZE,
        )
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="reward-referred",
    )

    referral = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
        reward_points=100,
        status=ReferralStatus.QUALIFIED,
    )

    rewarded = (
        await loyalty_referral_service.reward_referral(
            referral_id=referral.id,
        )
    )

    assert rewarded.status == (
        ReferralStatus.REWARDED
    )

    assert rewarded.rewarded_at is not None

    # ------------------------------------------------------
    # Verify Loyalty Account
    # ------------------------------------------------------

    await db_session.refresh(
        referrer_account,
    )

    assert referrer_account.points_balance == 100
    assert referrer_account.lifetime_points == 100
    assert referrer_account.tier == LoyaltyTier.BRONZE

    # ------------------------------------------------------
    # Verify Loyalty Ledger
    # ------------------------------------------------------

    result = await db_session.execute(
        select(
            LoyaltyPointTransaction,
        ).where(
            LoyaltyPointTransaction.loyalty_account_id
            == referrer_account.id,
            LoyaltyPointTransaction.reference_type
            == "LOYALTY_REFERRAL",
            LoyaltyPointTransaction.reference_id
            == referral.id,
        )
    )

    transaction = (
        result.scalars().first()
    )

    assert transaction is not None
    assert transaction.points == 100
    assert transaction.balance_after == 100

    assert transaction.transaction_type in {
        LoyaltyPointTransactionType.REFERRAL_BONUS,
        LoyaltyPointTransactionType.EARN,
    }

    print(
        "Referral reward -> LoyaltyService -> "
        "LoyaltyAccount + Ledger: OK"
    )


# ==========================================================
# Reward Validation
# ==========================================================


@pytest.mark.asyncio
async def test_reward_referral_rejects_pending_referral(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Pending referrals cannot be rewarded directly.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    referral = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
        status=ReferralStatus.PENDING,
    )

    with pytest.raises(
        BadRequestException,
        match="Only qualified referrals can be rewarded",
    ):
        await loyalty_referral_service.reward_referral(
            referral_id=referral.id,
        )

    print(
        "Pending referral reward correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_reward_referral_rejects_zero_reward(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    A qualified referral with zero reward points cannot
    be rewarded.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    referral = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
        status=ReferralStatus.QUALIFIED,
        reward_points=0,
    )

    with pytest.raises(
        BadRequestException,
        match="must be greater than zero",
    ):
        await loyalty_referral_service.reward_referral(
            referral_id=referral.id,
        )

    print(
        "Zero-point referral reward correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_reward_referral_rejects_already_rewarded(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    A rewarded referral cannot be rewarded again.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    referral = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
        status=ReferralStatus.REWARDED,
        reward_points=100,
    )

    with pytest.raises(
        BadRequestException,
        match="Only qualified referrals can be rewarded",
    ):
        await loyalty_referral_service.reward_referral(
            referral_id=referral.id,
        )

    print(
        "Duplicate referral reward correctly rejected: OK"
    )


# ==========================================================
# Cancellation
# ==========================================================


@pytest.mark.asyncio
async def test_cancel_pending_referral(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Verify PENDING → CANCELLED.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    referral = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
        status=ReferralStatus.PENDING,
    )

    cancelled = (
        await loyalty_referral_service.cancel_referral(
            referral_id=referral.id,
            reason="Customer cancelled referral.",
        )
    )

    assert cancelled.status == (
        ReferralStatus.CANCELLED
    )

    assert cancelled.cancelled_at is not None
    assert cancelled.notes == (
        "Customer cancelled referral."
    )

    print(
        "Pending referral cancellation: OK"
    )


@pytest.mark.asyncio
async def test_cancel_qualified_referral(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Verify QUALIFIED → CANCELLED.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    referral = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
        status=ReferralStatus.QUALIFIED,
    )

    cancelled = (
        await loyalty_referral_service.cancel_referral(
            referral_id=referral.id,
            reason="Qualification cancelled.",
        )
    )

    assert cancelled.status == (
        ReferralStatus.CANCELLED
    )

    assert cancelled.cancelled_at is not None

    print(
        "Qualified referral cancellation: OK"
    )


@pytest.mark.asyncio
async def test_cancel_rewarded_referral_rejected(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Rewarded referrals are terminal and cannot be cancelled.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    referral = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
        status=ReferralStatus.REWARDED,
    )

    with pytest.raises(
        BadRequestException,
        match="Only pending or qualified referrals",
    ):
        await loyalty_referral_service.cancel_referral(
            referral_id=referral.id,
        )

    print(
        "Rewarded referral cancellation correctly rejected: OK"
    )


# ==========================================================
# Active Referral
# ==========================================================


@pytest.mark.asyncio
async def test_get_active_referral_pending(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    PENDING referrals are active.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    referral = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
        status=ReferralStatus.PENDING,
    )

    active = (
        await loyalty_referral_service
        .get_active_referral(
            referral.id,
        )
    )

    assert active is not None
    assert active.id == referral.id
    assert active.status == ReferralStatus.PENDING

    print(
        "Pending referral active lookup: OK"
    )


@pytest.mark.asyncio
async def test_get_active_referral_qualified(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    QUALIFIED referrals are active.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    referral = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
        status=ReferralStatus.QUALIFIED,
    )

    active = (
        await loyalty_referral_service
        .get_active_referral(
            referral.id,
        )
    )

    assert active is not None
    assert active.status == ReferralStatus.QUALIFIED

    print(
        "Qualified referral active lookup: OK"
    )


@pytest.mark.asyncio
async def test_get_active_referral_rejects_rewarded(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    REWARDED referrals are no longer active.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="referred",
    )

    referral = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
        status=ReferralStatus.REWARDED,
    )

    with pytest.raises(
        NotFoundException,
        match="Active loyalty referral not found",
    ):
        await loyalty_referral_service.get_active_referral(
            referral.id,
        )

    print(
        "Rewarded referral correctly excluded from active: OK"
    )


# ==========================================================
# Customer History
# ==========================================================


@pytest.mark.asyncio
async def test_get_customer_referrals(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Verify customer referral history.

    A customer can appear as either:
    - referrer
    - referred customer
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="history-referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="history-referred",
    )

    referral = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
    )

    referrer_history = (
        await loyalty_referral_service
        .get_customer_referrals(
            referrer.id,
        )
    )

    referred_history = (
        await loyalty_referral_service
        .get_customer_referrals(
            referred.id,
        )
    )

    assert any(
        item.id == referral.id
        for item in referrer_history
    )

    assert any(
        item.id == referral.id
        for item in referred_history
    )

    print(
        "Customer referral history: OK"
    )


# ==========================================================
# Status Queries
# ==========================================================


@pytest.mark.asyncio
async def test_get_referrals_by_status(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Verify service status filtering.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="status-referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="status-referred",
    )

    referral = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
        status=ReferralStatus.QUALIFIED,
    )

    qualified = (
        await loyalty_referral_service
        .get_referrals_by_status(
            ReferralStatus.QUALIFIED,
        )
    )

    assert any(
        item.id == referral.id
        for item in qualified
    )

    print(
        "Referral status filtering through service: OK"
    )


# ==========================================================
# Pagination Validation
# ==========================================================


@pytest.mark.asyncio
async def test_get_customer_referrals_rejects_zero_limit(
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Pagination limit must be >= 1.
    """

    with pytest.raises(
        BadRequestException,
        match="Limit must be greater than zero",
    ):
        await loyalty_referral_service.get_customer_referrals(
            customer_id=1,
            limit=0,
        )

    print(
        "Zero pagination limit correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_get_customer_referrals_rejects_negative_offset(
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Pagination offset cannot be negative.
    """

    with pytest.raises(
        BadRequestException,
        match="Offset cannot be negative",
    ):
        await loyalty_referral_service.get_customer_referrals(
            customer_id=1,
            offset=-1,
        )

    print(
        "Negative pagination offset correctly rejected: OK"
    )


# ==========================================================
# Status Transition Tests
# ==========================================================


@pytest.mark.asyncio
async def test_update_status_pending_to_qualified(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Verify controlled transition:

        PENDING → QUALIFIED
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="transition-referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="transition-referred",
    )

    referral = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
        status=ReferralStatus.PENDING,
    )

    updated = (
        await loyalty_referral_service.update_status(
            referral_id=referral.id,
            status=ReferralStatus.QUALIFIED,
        )
    )

    assert updated.status == (
        ReferralStatus.QUALIFIED
    )

    assert updated.qualified_at is not None

    print(
        "PENDING -> QUALIFIED transition: OK"
    )


@pytest.mark.asyncio
async def test_update_status_qualified_to_rewarded(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Verify controlled transition:

        QUALIFIED → REWARDED

    and verify loyalty points are awarded.
    """

    referrer, account = (
        await create_customer_with_account(
            db_session,
            prefix="reward-transition-referrer",
            points_balance=0,
            lifetime_points=0,
            tier=LoyaltyTier.BRONZE,
        )
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="reward-transition-referred",
    )

    referral = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
        status=ReferralStatus.QUALIFIED,
        reward_points=150,
    )

    updated = (
        await loyalty_referral_service.update_status(
            referral_id=referral.id,
            status=ReferralStatus.REWARDED,
        )
    )

    assert updated.status == (
        ReferralStatus.REWARDED
    )

    assert updated.rewarded_at is not None

    await db_session.refresh(account)

    assert account.points_balance == 150
    assert account.lifetime_points == 150

    print(
        "QUALIFIED -> REWARDED + points award: OK"
    )


@pytest.mark.asyncio
async def test_update_status_pending_to_cancelled(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Verify controlled transition:

        PENDING → CANCELLED
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="cancel-transition-referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="cancel-transition-referred",
    )

    referral = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
        status=ReferralStatus.PENDING,
    )

    updated = (
        await loyalty_referral_service.update_status(
            referral_id=referral.id,
            status=ReferralStatus.CANCELLED,
        )
    )

    assert updated.status == (
        ReferralStatus.CANCELLED
    )

    assert updated.cancelled_at is not None

    print(
        "PENDING -> CANCELLED transition: OK"
    )


@pytest.mark.asyncio
async def test_update_status_rewarded_to_pending_rejected(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Terminal REWARDED referrals cannot move backwards.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="terminal-referrer",
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="terminal-referred",
    )

    referral = await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred.id,
        status=ReferralStatus.REWARDED,
    )

    with pytest.raises(
        BadRequestException,
        match="terminal state",
    ):
        await loyalty_referral_service.update_status(
            referral_id=referral.id,
            status=ReferralStatus.PENDING,
        )

    print(
        "REWARDED terminal transition correctly rejected: OK"
    )


# ==========================================================
# Statistics
# ==========================================================


@pytest.mark.asyncio
async def test_get_customer_statistics(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Verify customer referral statistics.
    """

    referrer, _ = await create_customer_with_account(
        db_session,
        prefix="stats-referrer",
    )

    referred_one, _ = (
        await create_customer_with_account(
            db_session,
            prefix="stats-referred-one",
        )
    )

    referred_two, _ = (
        await create_customer_with_account(
            db_session,
            prefix="stats-referred-two",
        )
    )

    referred_three, _ = (
        await create_customer_with_account(
            db_session,
            prefix="stats-referred-three",
        )
    )

    await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred_one.id,
        status=ReferralStatus.PENDING,
        reward_points=100,
    )

    await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred_two.id,
        status=ReferralStatus.QUALIFIED,
        reward_points=150,
    )

    await create_test_referral(
        db_session,
        referrer_id=referrer.id,
        referred_id=referred_three.id,
        status=ReferralStatus.REWARDED,
        reward_points=200,
    )

    statistics = (
        await loyalty_referral_service
        .get_customer_statistics(
            referrer.id,
        )
    )

    assert statistics["total_referrals"] == 3
    assert statistics["pending_referrals"] == 1
    assert statistics["qualified_referrals"] == 1
    assert statistics["rewarded_referrals"] == 1
    assert statistics["cancelled_referrals"] == 0
    assert statistics["total_reward_points"] == 200

    print(
        "Customer referral statistics: OK"
    )


# ==========================================================
# Complete Lifecycle Integration Test
# ==========================================================


@pytest.mark.asyncio
async def test_complete_referral_lifecycle(
    db_session: AsyncSession,
    loyalty_referral_service: LoyaltyReferralService,
):
    """
    Complete end-to-end service lifecycle.

        Create
          ↓
        Validate
          ↓
        Qualify
          ↓
        Reward
          ↓
        Loyalty Account Updated
          ↓
        Loyalty Ledger Created
          ↓
        Referral No Longer Active
    """

    referrer, account = (
        await create_customer_with_account(
            db_session,
            prefix="lifecycle-referrer",
            points_balance=0,
            lifetime_points=0,
            tier=LoyaltyTier.BRONZE,
        )
    )

    referred, _ = await create_customer_with_account(
        db_session,
        prefix="lifecycle-referred",
    )

    # ------------------------------------------------------
    # Create
    # ------------------------------------------------------

    referral_code = (
        f"REF-LIFECYCLE-{uuid4().hex[:12].upper()}"
    )

    referral = (
        await loyalty_referral_service.create_referral(
            referrer_id=referrer.id,
            referred_id=referred.id,
            referral_code=referral_code,
            reward_points=250,
            notes="Complete lifecycle test",
        )
    )

    assert referral.status == (
        ReferralStatus.PENDING
    )

    print("Lifecycle - create: OK")

    # ------------------------------------------------------
    # Validate
    # ------------------------------------------------------

    result = (
        await loyalty_referral_service
        .validate_referral_code(
            customer_id=referred.id,
            referral_code=referral_code,
        )
    )

    found, valid, exists, active, reason = result

    assert found is not None
    assert found.id == referral.id
    assert valid is True
    assert exists is True
    assert active is True
    assert reason is None

    # ------------------------------------------------------
    # Qualify
    # ------------------------------------------------------

    qualified_referral = (
        await loyalty_referral_service.qualify_referral(
            referral_id=referral.id,
        )
    )

    assert qualified_referral is not None
    assert qualified_referral.id == referral.id
    assert qualified_referral.status == (
        ReferralStatus.QUALIFIED
    )
    assert qualified_referral.qualified_at is not None

    print("Lifecycle - qualification: OK")

    # ------------------------------------------------------
    # Confirm Active
    # ------------------------------------------------------

    active_referral = (
        await loyalty_referral_service.get_active_referral(
            referral.id,
        )
    )

    assert active_referral is not None
    assert active_referral.id == referral.id
    assert active_referral.status == (
        ReferralStatus.QUALIFIED
    )

    print("Lifecycle - active qualified referral: OK")

    # ------------------------------------------------------
    # Reward
    # ------------------------------------------------------

    referral = (
        await loyalty_referral_service.reward_referral(
            referral_id=referral.id,
        )
    )

    assert referral.status == (
        ReferralStatus.REWARDED
    )

    assert referral.rewarded_at is not None

    print("Lifecycle - reward: OK")

    # ------------------------------------------------------
    # Verify Loyalty Account
    # ------------------------------------------------------

    await db_session.refresh(
        account,
    )

    assert account.points_balance == 250
    assert account.lifetime_points == 250
    assert account.tier == LoyaltyTier.BRONZE

    print(
        "Lifecycle - loyalty account update: OK"
    )

    # ------------------------------------------------------
    # Verify Ledger
    # ------------------------------------------------------

    result = await db_session.execute(
        select(
            LoyaltyPointTransaction,
        ).where(
            LoyaltyPointTransaction.loyalty_account_id
            == account.id,
            LoyaltyPointTransaction.reference_type
            == "LOYALTY_REFERRAL",
            LoyaltyPointTransaction.reference_id
            == referral.id,
        )
    )

    transaction = (
        result.scalars().first()
    )

    assert transaction is not None
    assert transaction.points == 250
    assert transaction.balance_after == 250

    print(
        "Lifecycle - loyalty ledger transaction: OK"
    )

    # ------------------------------------------------------
    # Verify No Longer Active
    # ------------------------------------------------------

    with pytest.raises(
        NotFoundException,
        match="Active loyalty referral not found",
    ):
        await loyalty_referral_service.get_active_referral(
            referral.id,
        )

    print(
        "Lifecycle - rewarded referral inactive: OK"
    )

    # ------------------------------------------------------
    # Final Verification
    # ------------------------------------------------------

    final_referral = (
        await loyalty_referral_service.get_referral(
            referral.id,
        )
    )

    assert final_referral.status == (
        ReferralStatus.REWARDED
    )

    assert final_referral.reward_points == 250

    print(
        "\n"
        "====================================================\n"
        "Loyalty Referral Service Integration Test\n"
        "SERVICE -> REPOSITORY -> LOYALTY SERVICE -> DB\n"
        "COMPLETE REFERRAL LIFECYCLE: PASSED\n"
        "===================================================="
    )