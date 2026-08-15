"""
Loyalty Coupon Service Integration Tests.

Tests the LoyaltyCouponService business rules against the
real PostgreSQL test database.

Architecture under test
-----------------------

    Test
      |
      v
LoyaltyCouponService
      |
      +----------------------+
      |                      |
      v                      v
LoyaltyService       LoyaltyCouponRepository
      |                      |
      v                      v
LoyaltyRepository      PostgreSQL
      |
      v
PostgreSQL


The tests intentionally use the real PostgreSQL test database.

Repository persistence behaviour is covered separately by:

    test_loyalty_coupon_repository.py

These tests focus on:

- Coupon creation
- Coupon validation
- Coupon ownership
- Coupon validity periods
- Coupon status
- Coupon usage
- Duplicate coupon usage
- Customer coupon retrieval
- Coupon filtering
- Coupon counts
- Coupon updates
- Coupon deletion rules
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

from app.exceptions.handlers import (
    BadRequestException,
    NotFoundException,
)

from app.models.enums import (
    CouponStatus,
    CouponType,
    Currency,
    LoyaltyTier,
    PaymentMethod,
    PaymentProvider,
    PaymentPurpose,
    PaymentStatus,
    PaymentType,
    UserRole,
)

from app.models.loyalty_account import (
    LoyaltyAccount,
)

from app.models.loyalty_coupon import (
    LoyaltyCoupon,
)

from app.models.payment_transaction import (
    PaymentTransaction,
)

from app.models.user import (
    User,
)

from app.repositories.loyalty_coupon_repository import (
    LoyaltyCouponRepository,
)

from app.repositories.loyalty_repository import (
    LoyaltyRepository,
)

from app.services.loyalty_coupon_service import (
    LoyaltyCouponService,
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

    Uses TEST_DATABASE_URL so service integration tests
    execute against the dedicated PostgreSQL test database.
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
async def loyalty_coupon_service(
    db_session: AsyncSession,
) -> LoyaltyCouponService:
    """
    Create a real LoyaltyCouponService backed by:

        LoyaltyService
            +
        LoyaltyCouponRepository
            +
        PostgreSQL
    """

    coupon_repository = LoyaltyCouponRepository(
        db=db_session,
    )

    loyalty_repository = LoyaltyRepository(
        db=db_session,
    )

    loyalty_service = LoyaltyService(
        db=db_session,
        repository=loyalty_repository,
    )

    return LoyaltyCouponService(
        db=db_session,
        repository=coupon_repository,
        loyalty_service=loyalty_service,
    )


# ==========================================================
# Test User Factory
# ==========================================================


async def create_test_user(
    db: AsyncSession,
) -> User:
    """
    Create a unique real test customer.
    """

    unique_id = uuid4().hex[:10].lower()

    user = User(
        first_name="Coupon",
        last_name="Service Test",
        email=(
            f"coupon.service.{unique_id}"
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
# Loyalty Account Factory
# ==========================================================


async def create_test_loyalty_account(
    db: AsyncSession,
    *,
    customer_id: int,
    points_balance: int = 5000,
    lifetime_points: int = 5000,
    tier: LoyaltyTier = LoyaltyTier.GOLD,
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
# Payment Transaction Factory
# ==========================================================


async def create_test_payment_transaction(
    db: AsyncSession,
    *,
    customer_id: int,
) -> PaymentTransaction:
    """
    Create a real payment transaction in PostgreSQL.

    LoyaltyCoupon.used_payment_transaction_id is a real
    foreign key to payment_transactions.id, so service tests
    must use an actual persisted payment transaction rather
    than an arbitrary integer.
    """

    unique_id = uuid4().hex[:12].upper()

    payment = PaymentTransaction(
        transaction_number=f"PAY-SVC-IT-{unique_id}",
        reservation_id=None,
        parking_session_id=None,
        customer_id=customer_id,
        parent_transaction_id=None,
        payment_type=PaymentType.PAYMENT,
        payment_purpose=PaymentPurpose.PARKING_SESSION,
        payment_method=PaymentMethod.CASH,
        payment_provider=PaymentProvider.INTERNAL,
        status=PaymentStatus.SUCCESSFUL,
        currency=Currency.KES,
        subtotal_amount=Decimal("100.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("100.00"),
        payer_name="Coupon Service Test",
        payer_phone=None,
        payer_email=None,
        paid_at=datetime.now(timezone.utc),
        notes="Loyalty coupon service integration test payment",
    )

    db.add(payment)
    await db.flush()
    await db.refresh(payment)

    assert payment.id is not None

    return payment


# ==========================================================
# Coupon Factory
# ==========================================================


async def create_test_coupon(
    db: AsyncSession,
    *,
    loyalty_account_id: int,
    coupon_code: str | None = None,
    coupon_type: CouponType = (
        CouponType.FIXED_AMOUNT_DISCOUNT
    ),
    value: Decimal | None = Decimal("100.00"),
    free_parking_minutes: int | None = None,
    status: CouponStatus = CouponStatus.ACTIVE,
    is_active: bool = True,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    reward_redemption_id: int | None = None,
    used_at: datetime | None = None,
    used_payment_transaction_id: int | None = None,
    description: str = "Service integration test coupon",
) -> LoyaltyCoupon:
    """
    Create a coupon directly in PostgreSQL.

    Used when the service test needs a coupon in a specific
    state, such as USED, EXPIRED or FUTURE.
    """

    unique_id = uuid4().hex[:10].upper()

    if coupon_code is None:
        coupon_code = (
            f"SP-SVC-{unique_id}"
        )

    coupon = LoyaltyCoupon(
        coupon_code=coupon_code,
        loyalty_account_id=loyalty_account_id,
        reward_redemption_id=reward_redemption_id,
        coupon_type=coupon_type,
        value=value,
        free_parking_minutes=free_parking_minutes,
        status=status,
        is_active=is_active,
        valid_from=valid_from,
        valid_until=valid_until,
        used_at=used_at,
        used_payment_transaction_id=(
            used_payment_transaction_id
        ),
        description=description,
    )

    db.add(coupon)

    await db.flush()
    await db.refresh(coupon)

    return coupon


# ==========================================================
# Customer Fixture Helper
# ==========================================================


async def create_customer_with_account(
    db: AsyncSession,
    *,
    points_balance: int = 5000,
    lifetime_points: int = 5000,
    tier: LoyaltyTier = LoyaltyTier.GOLD,
    is_active: bool = True,
) -> tuple[User, LoyaltyAccount]:
    """
    Create a customer and loyalty account.
    """

    user = await create_test_user(
        db,
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
# Creation Tests
# ==========================================================


@pytest.mark.asyncio
async def test_create_coupon(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Verify the service creates a valid customer coupon.
    """

    user, account = await create_customer_with_account(
        db_session,
    )

    coupon = await loyalty_coupon_service.create_coupon(
        customer_id=user.id,
        coupon_type=CouponType.FIXED_AMOUNT_DISCOUNT,
        value=Decimal("100.00"),
        description="KES 100 service test coupon",
    )

    assert coupon is not None
    assert coupon.id is not None
    assert coupon.loyalty_account_id == account.id
    assert coupon.coupon_type == (
        CouponType.FIXED_AMOUNT_DISCOUNT
    )
    assert coupon.value == Decimal("100.00")
    assert coupon.status == CouponStatus.ACTIVE
    assert coupon.is_active is True
    assert coupon.coupon_code.startswith(
        "SP-COUPON-"
    )

    print(
        "Create coupon through service: OK"
    )


@pytest.mark.asyncio
async def test_create_coupon_with_supplied_code(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Verify the service accepts an explicitly supplied
    coupon code.
    """

    user, _ = await create_customer_with_account(
        db_session,
    )

    supplied_code = (
        f"SP-SERVICE-CREATE-{uuid4().hex[:12].upper()}"
    )

    coupon = await loyalty_coupon_service.create_coupon(
        customer_id=user.id,
        coupon_code=supplied_code,
        coupon_type=CouponType.FIXED_AMOUNT_DISCOUNT,
        value=Decimal("250.00"),
    )

    assert coupon.coupon_code == supplied_code

    print(
        "Create coupon with supplied code: OK"
    )


@pytest.mark.asyncio
async def test_create_coupon_duplicate_code_rejected(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Verify duplicate coupon codes are rejected by the
    service before persistence.
    """

    user, account = await create_customer_with_account(
        db_session,
    )

    duplicate_code = f"SP-SERVICE-DUPLICATE-{uuid4().hex[:12].upper()}"

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_code=duplicate_code,
    )

    await db_session.commit()

    with pytest.raises(
        BadRequestException,
        match="Coupon code already exists.",
    ):
        await loyalty_coupon_service.create_coupon(
            customer_id=user.id,
            coupon_code=duplicate_code,
            coupon_type=(
                CouponType.FIXED_AMOUNT_DISCOUNT
            ),
            value=Decimal("100.00"),
        )

    print(
        "Duplicate coupon code correctly rejected: OK"
    )


# ==========================================================
# Creation Validation
# ==========================================================


@pytest.mark.asyncio
async def test_create_coupon_requires_discount_value(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Discount coupons must have a positive value.
    """

    user, _ = await create_customer_with_account(
        db_session,
    )

    with pytest.raises(
        BadRequestException,
        match="Coupon value is required",
    ):
        await loyalty_coupon_service.create_coupon(
            customer_id=user.id,
            coupon_type=(
                CouponType.FIXED_AMOUNT_DISCOUNT
            ),
            value=None,
        )

    print(
        "Discount coupon value validation: OK"
    )


@pytest.mark.asyncio
async def test_percentage_coupon_cannot_exceed_100(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Percentage discounts above 100% must be rejected.
    """

    user, _ = await create_customer_with_account(
        db_session,
    )

    with pytest.raises(
        BadRequestException,
        match="Percentage discount cannot exceed 100",
    ):
        await loyalty_coupon_service.create_coupon(
            customer_id=user.id,
            coupon_type=(
                CouponType.PERCENTAGE_DISCOUNT
            ),
            value=Decimal("101.00"),
        )

    print(
        "Percentage coupon >100% correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_free_parking_coupon_requires_minutes(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    FREE_PARKING_HOURS coupons must specify parking minutes.
    """

    user, _ = await create_customer_with_account(
        db_session,
    )

    with pytest.raises(
        BadRequestException,
        match="Free parking minutes are required",
    ):
        await loyalty_coupon_service.create_coupon(
            customer_id=user.id,
            coupon_type=CouponType.FREE_PARKING_HOURS,
            value=None,
            free_parking_minutes=None,
        )

    print(
        "Free parking minutes validation: OK"
    )


@pytest.mark.asyncio
async def test_invalid_validity_period_rejected(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    valid_until cannot be earlier than valid_from.
    """

    user, _ = await create_customer_with_account(
        db_session,
    )

    valid_from = datetime.now(
        timezone.utc,
    )

    valid_until = (
        valid_from - timedelta(days=1)
    )

    with pytest.raises(
        BadRequestException,
        match="valid_until cannot be earlier than valid_from",
    ):
        await loyalty_coupon_service.create_coupon(
            customer_id=user.id,
            coupon_type=(
                CouponType.FIXED_AMOUNT_DISCOUNT
            ),
            value=Decimal("100.00"),
            valid_from=valid_from,
            valid_until=valid_until,
        )

    print(
        "Invalid coupon validity period rejected: OK"
    )


# ==========================================================
# Account Validation
# ==========================================================


@pytest.mark.asyncio
async def test_create_coupon_requires_loyalty_account(
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    A customer without a loyalty account cannot receive
    a coupon.
    """

    with pytest.raises(
        NotFoundException,
        match="Loyalty account not found.",
    ):
        await loyalty_coupon_service.create_coupon(
            customer_id=999999999,
            coupon_type=(
                CouponType.FIXED_AMOUNT_DISCOUNT
            ),
            value=Decimal("100.00"),
        )

    print(
        "Customer without loyalty account rejected: OK"
    )


@pytest.mark.asyncio
async def test_create_coupon_rejects_inactive_account(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Coupons cannot be created for an inactive loyalty account.
    """

    user, _ = await create_customer_with_account(
        db_session,
        is_active=False,
    )

    with pytest.raises(
        BadRequestException,
        match="Customer loyalty account is inactive",
    ):
        await loyalty_coupon_service.create_coupon(
            customer_id=user.id,
            coupon_type=(
                CouponType.FIXED_AMOUNT_DISCOUNT
            ),
            value=Decimal("100.00"),
        )

    print(
        "Inactive loyalty account correctly rejected: OK"
    )


# ==========================================================
# Retrieval Tests
# ==========================================================


@pytest.mark.asyncio
async def test_get_coupon(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Verify coupon retrieval by ID.
    """

    user, account = await create_customer_with_account(
        db_session,
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
    )

    await db_session.commit()

    result = await loyalty_coupon_service.get_coupon(
        coupon.id,
    )

    assert result is not None
    assert result.id == coupon.id

    print(
        "Get coupon through service: OK"
    )


@pytest.mark.asyncio
async def test_get_coupon_not_found(
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Verify missing coupon raises NotFoundException.
    """

    with pytest.raises(
        NotFoundException,
        match="Loyalty coupon not found.",
    ):
        await loyalty_coupon_service.get_coupon(
            999999999,
        )

    print(
        "Missing coupon correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_get_coupon_by_code(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Verify coupon lookup by code.
    """

    _, account = await create_customer_with_account(
        db_session,
    )

    lookup_code = (
        f"SP-SERVICE-LOOKUP-{uuid4().hex[:12].upper()}"
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_code=lookup_code,
    )

    await db_session.commit()

    result = (
        await loyalty_coupon_service.get_coupon_by_code(
            lookup_code,
        )
    )

    assert result.id == coupon.id

    print(
        "Get coupon by code through service: OK"
    )


@pytest.mark.asyncio
async def test_get_coupon_by_code_not_found(
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Verify missing coupon code raises NotFoundException.
    """

    with pytest.raises(
        NotFoundException,
        match="Loyalty coupon not found.",
    ):
        await loyalty_coupon_service.get_coupon_by_code(
            "SP-NOT-FOUND-999",
        )

    print(
        "Missing coupon code correctly rejected: OK"
    )


# ==========================================================
# Customer Ownership Tests
# ==========================================================


@pytest.mark.asyncio
async def test_customer_can_retrieve_own_coupon(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Verify a customer can retrieve their own coupon.
    """

    user, account = await create_customer_with_account(
        db_session,
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
    )

    await db_session.commit()

    result = (
        await loyalty_coupon_service.get_customer_coupon(
            customer_id=user.id,
            coupon_id=coupon.id,
        )
    )

    assert result.id == coupon.id
    assert result.loyalty_account_id == account.id

    print(
        "Customer ownership validation: OK"
    )


@pytest.mark.asyncio
async def test_customer_cannot_retrieve_another_customers_coupon(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Verify customer A cannot retrieve customer B's coupon.
    """

    customer_a, _ = await create_customer_with_account(
        db_session,
    )

    customer_b, account_b = (
        await create_customer_with_account(
            db_session,
        )
    )

    coupon_b = await create_test_coupon(
        db_session,
        loyalty_account_id=account_b.id,
    )

    await db_session.commit()

    with pytest.raises(
        NotFoundException,
        match="Loyalty coupon not found.",
    ):
        await loyalty_coupon_service.get_customer_coupon(
            customer_id=customer_a.id,
            coupon_id=coupon_b.id,
        )

    print(
        "Cross-customer coupon access correctly rejected: OK"
    )


# ==========================================================
# Customer Coupon Listing
# ==========================================================


@pytest.mark.asyncio
async def test_get_customer_coupons(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Verify customer coupon history retrieval.
    """

    user, account = await create_customer_with_account(
        db_session,
    )

    first = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
    )

    second = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
    )

    await db_session.commit()

    results = (
        await loyalty_coupon_service.get_customer_coupons(
            customer_id=user.id,
        )
    )

    ids = {
        coupon.id
        for coupon in results
    }

    assert first.id in ids
    assert second.id in ids

    print(
        "Customer coupon history retrieval: OK"
    )


@pytest.mark.asyncio
async def test_get_customer_coupons_pagination_validation(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Verify invalid pagination parameters are rejected.
    """

    user, _ = await create_customer_with_account(
        db_session,
    )

    with pytest.raises(
        BadRequestException,
        match="Limit must be greater than zero",
    ):
        await loyalty_coupon_service.get_customer_coupons(
            customer_id=user.id,
            limit=0,
        )

    with pytest.raises(
        BadRequestException,
        match="Offset cannot be negative",
    ):
        await loyalty_coupon_service.get_customer_coupons(
            customer_id=user.id,
            offset=-1,
        )

    print(
        "Coupon pagination validation: OK"
    )


# ==========================================================
# Coupon Validation
# ==========================================================


@pytest.mark.asyncio
async def test_validate_active_coupon(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Verify an active, valid coupon passes validation.
    """

    user, account = await create_customer_with_account(
        db_session,
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        valid_from=(
            datetime.now(timezone.utc)
            - timedelta(days=1)
        ),
        valid_until=(
            datetime.now(timezone.utc)
            + timedelta(days=1)
        ),
    )

    await db_session.commit()

    result = await loyalty_coupon_service.validate_coupon(
        customer_id=user.id,
        coupon_code=coupon.coupon_code,
    )

    assert result.id == coupon.id
    assert result.status == CouponStatus.ACTIVE
    assert result.is_active is True

    print(
        "Active coupon validation: OK"
    )


@pytest.mark.asyncio
async def test_validate_used_coupon_rejected(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    USED coupons cannot be validated for reuse.
    """

    user, account = await create_customer_with_account(
        db_session,
    )

    payment = await create_test_payment_transaction(
        db_session,
        customer_id=user.id,
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        status=CouponStatus.USED,
        is_active=False,
        used_at=datetime.now(timezone.utc),
        used_payment_transaction_id=payment.id,
    )

    await db_session.commit()

    with pytest.raises(
        BadRequestException,
        match="coupon is not active",
    ):
        await loyalty_coupon_service.validate_coupon(
            customer_id=user.id,
            coupon_code=coupon.coupon_code,
        )

    print(
        "Used coupon reuse correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_validate_expired_coupon_rejected(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Expired coupons cannot be validated.
    """

    user, account = await create_customer_with_account(
        db_session,
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        valid_from=(
            datetime.now(timezone.utc)
            - timedelta(days=10)
        ),
        valid_until=(
            datetime.now(timezone.utc)
            - timedelta(days=1)
        ),
    )

    await db_session.commit()

    with pytest.raises(
        BadRequestException,
        match="coupon has expired",
    ):
        await loyalty_coupon_service.validate_coupon(
            customer_id=user.id,
            coupon_code=coupon.coupon_code,
        )

    print(
        "Expired coupon correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_validate_future_coupon_rejected(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Coupons whose validity period has not started cannot
    be used.
    """

    user, account = await create_customer_with_account(
        db_session,
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        valid_from=(
            datetime.now(timezone.utc)
            + timedelta(days=1)
        ),
        valid_until=(
            datetime.now(timezone.utc)
            + timedelta(days=10)
        ),
    )

    await db_session.commit()

    with pytest.raises(
        BadRequestException,
        match="coupon is not yet valid",
    ):
        await loyalty_coupon_service.validate_coupon(
            customer_id=user.id,
            coupon_code=coupon.coupon_code,
        )

    print(
        "Future coupon correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_validate_inactive_coupon_rejected(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    A disabled coupon cannot be used.
    """

    user, account = await create_customer_with_account(
        db_session,
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        status=CouponStatus.ACTIVE,
        is_active=False,
    )

    await db_session.commit()

    with pytest.raises(
        BadRequestException,
        match="coupon is currently disabled",
    ):
        await loyalty_coupon_service.validate_coupon(
            customer_id=user.id,
            coupon_code=coupon.coupon_code,
        )

    print(
        "Inactive coupon correctly rejected: OK"
    )


# ==========================================================
# Coupon Usage
# ==========================================================


@pytest.mark.asyncio
async def test_use_coupon(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Verify successful coupon usage.

    Expected lifecycle:

        ACTIVE
           |
           v
         USED
           |
           +--> is_active = False
           +--> used_at populated
           +--> payment transaction linked
    """

    user, account = await create_customer_with_account(
        db_session,
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
    )

    await db_session.commit()

    payment = await create_test_payment_transaction(
        db_session,
        customer_id=user.id,
    )

    payment_transaction_id = payment.id

    result = await loyalty_coupon_service.use_coupon(
        customer_id=user.id,
        coupon_code=coupon.coupon_code,
        payment_transaction_id=payment_transaction_id,
    )

    assert result.id == coupon.id
    assert result.status == CouponStatus.USED
    assert result.is_active is False
    assert result.used_at is not None
    assert result.used_payment_transaction_id == (
        payment_transaction_id
    )

    print(
        "Coupon usage lifecycle: OK"
    )


@pytest.mark.asyncio
async def test_use_coupon_wrong_customer_rejected(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    A customer cannot use another customer's coupon.
    """

    customer_a, _ = await create_customer_with_account(
        db_session,
    )

    customer_b, account_b = (
        await create_customer_with_account(
            db_session,
        )
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account_b.id,
    )

    await db_session.commit()

    with pytest.raises(
        BadRequestException,
        match="does not belong",
    ):
        await loyalty_coupon_service.use_coupon(
            customer_id=customer_a.id,
            coupon_code=coupon.coupon_code,
            payment_transaction_id=900002,
        )

    print(
        "Wrong customer coupon usage correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_use_coupon_already_used_rejected(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    A previously used coupon cannot be reused.
    """

    user, account = await create_customer_with_account(
        db_session,
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        status=CouponStatus.USED,
        is_active=False,
        used_at=datetime.now(timezone.utc),
        used_payment_transaction_id=(
            await create_test_payment_transaction(
                db_session,
                customer_id=user.id,
            )
        ).id,
    )

    await db_session.commit()

    with pytest.raises(
        BadRequestException,
        match="coupon is not active",
    ):
        await loyalty_coupon_service.use_coupon(
            customer_id=user.id,
            coupon_code=coupon.coupon_code,
            payment_transaction_id=900004,
        )

    print(
        "Already-used coupon correctly rejected: OK"
    )


@pytest.mark.asyncio
async def test_use_coupon_invalid_payment_id_rejected(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Invalid payment transaction IDs must be rejected.
    """

    user, account = await create_customer_with_account(
        db_session,
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
    )

    await db_session.commit()

    with pytest.raises(
        BadRequestException,
        match="Payment transaction ID must be greater",
    ):
        await loyalty_coupon_service.use_coupon(
            customer_id=user.id,
            coupon_code=coupon.coupon_code,
            payment_transaction_id=0,
        )

    print(
        "Invalid payment transaction ID rejected: OK"
    )


# ==========================================================
# Filtering
# ==========================================================


@pytest.mark.asyncio
async def test_get_customer_coupons_by_status(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Verify customer coupon status filtering.
    """

    user, account = await create_customer_with_account(
        db_session,
    )

    active_coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        status=CouponStatus.ACTIVE,
    )

    used_payment = await create_test_payment_transaction(
        db_session,
        customer_id=user.id,
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        status=CouponStatus.USED,
        is_active=False,
        used_at=datetime.now(timezone.utc),
        used_payment_transaction_id=used_payment.id,
    )

    await db_session.commit()

    results = (
        await loyalty_coupon_service
        .get_customer_coupons_by_status(
            customer_id=user.id,
            status=CouponStatus.ACTIVE,
        )
    )

    ids = {
        coupon.id
        for coupon in results
    }

    assert active_coupon.id in ids

    assert all(
        coupon.status == CouponStatus.ACTIVE
        for coupon in results
    )

    print(
        "Customer coupon status filtering: OK"
    )


@pytest.mark.asyncio
async def test_get_customer_coupons_by_type(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Verify customer coupon type filtering.
    """

    user, account = await create_customer_with_account(
        db_session,
    )

    fixed_coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_type=(
            CouponType.FIXED_AMOUNT_DISCOUNT
        ),
        value=Decimal("100.00"),
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_type=(
            CouponType.PERCENTAGE_DISCOUNT
        ),
        value=Decimal("20.00"),
    )

    await db_session.commit()

    results = (
        await loyalty_coupon_service
        .get_customer_coupons_by_type(
            customer_id=user.id,
            coupon_type=(
                CouponType.FIXED_AMOUNT_DISCOUNT
            ),
        )
    )

    ids = {
        coupon.id
        for coupon in results
    }

    assert fixed_coupon.id in ids

    assert all(
        coupon.coupon_type
        == CouponType.FIXED_AMOUNT_DISCOUNT
        for coupon in results
    )

    print(
        "Customer coupon type filtering: OK"
    )


# ==========================================================
# Active Coupon Retrieval
# ==========================================================


@pytest.mark.asyncio
async def test_get_active_customer_coupons(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Verify active and currently-valid coupons are returned.
    """

    user, account = await create_customer_with_account(
        db_session,
    )

    active_coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        status=CouponStatus.ACTIVE,
        is_active=True,
        valid_from=(
            datetime.now(timezone.utc)
            - timedelta(days=1)
        ),
        valid_until=(
            datetime.now(timezone.utc)
            + timedelta(days=1)
        ),
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        status=CouponStatus.USED,
        is_active=False,
        used_at=datetime.now(timezone.utc),
        used_payment_transaction_id=(
            await create_test_payment_transaction(
                db_session,
                customer_id=user.id,
            )
        ).id,
    )

    await db_session.commit()

    results = (
        await loyalty_coupon_service
        .get_active_customer_coupons(
            customer_id=user.id,
        )
    )

    ids = {
        coupon.id
        for coupon in results
    }

    assert active_coupon.id in ids

    assert all(
        coupon.status == CouponStatus.ACTIVE
        for coupon in results
    )

    print(
        "Active customer coupons: OK"
    )


# ==========================================================
# Counts
# ==========================================================


@pytest.mark.asyncio
async def test_count_customer_coupons(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Verify customer coupon count.
    """

    user, account = await create_customer_with_account(
        db_session,
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

    count = (
        await loyalty_coupon_service
        .count_customer_coupons(
            customer_id=user.id,
        )
    )

    assert count >= 2

    print(
        "Customer coupon count: OK"
    )


@pytest.mark.asyncio
async def test_count_customer_coupons_by_status(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Verify customer coupon counts can be filtered by status.
    """

    user, account = await create_customer_with_account(
        db_session,
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        status=CouponStatus.ACTIVE,
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        status=CouponStatus.ACTIVE,
    )

    await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        status=CouponStatus.USED,
        is_active=False,
        used_at=datetime.now(timezone.utc),
        used_payment_transaction_id=(
            await create_test_payment_transaction(
                db_session,
                customer_id=user.id,
            )
        ).id,
    )

    await db_session.commit()

    count = (
        await loyalty_coupon_service
        .count_customer_coupons_by_status(
            customer_id=user.id,
            status=CouponStatus.ACTIVE,
        )
    )

    assert count >= 2

    print(
        "Customer coupon count by status: OK"
    )


# ==========================================================
# Update
# ==========================================================


@pytest.mark.asyncio
async def test_update_coupon(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Verify coupon updates are validated and persisted.
    """

    _, account = await create_customer_with_account(
        db_session,
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        value=Decimal("100.00"),
    )

    await db_session.commit()

    updated = await loyalty_coupon_service.update_coupon(
        coupon.id,
        value=Decimal("150.00"),
        description="Updated service coupon",
    )

    assert updated.id == coupon.id
    assert updated.value == Decimal("150.00")
    assert updated.description == (
        "Updated service coupon"
    )

    print(
        "Coupon update through service: OK"
    )


@pytest.mark.asyncio
async def test_update_coupon_rejects_invalid_percentage(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Verify coupon updates cannot introduce an invalid
    percentage discount.
    """

    _, account = await create_customer_with_account(
        db_session,
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        coupon_type=(
            CouponType.PERCENTAGE_DISCOUNT
        ),
        value=Decimal("20.00"),
    )

    await db_session.commit()

    with pytest.raises(
        BadRequestException,
        match="Percentage discount cannot exceed 100",
    ):
        await loyalty_coupon_service.update_coupon(
            coupon.id,
            value=Decimal("101.00"),
        )

    print(
        "Invalid coupon update correctly rejected: OK"
    )


# ==========================================================
# Status Management
# ==========================================================


@pytest.mark.asyncio
async def test_update_coupon_status(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Verify coupon status can be changed.
    """

    _, account = await create_customer_with_account(
        db_session,
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
    )

    await db_session.commit()

    updated = (
        await loyalty_coupon_service
        .update_coupon_status(
            coupon.id,
            status=CouponStatus.CANCELLED,
            is_active=False,
        )
    )

    assert updated.status == (
        CouponStatus.CANCELLED
    )
    assert updated.is_active is False

    print(
        "Coupon status update: OK"
    )


# ==========================================================
# Delete
# ==========================================================


@pytest.mark.asyncio
async def test_delete_active_coupon(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Verify an unused coupon can be deleted.
    """

    _, account = await create_customer_with_account(
        db_session,
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
    )

    await db_session.commit()

    await loyalty_coupon_service.delete_coupon(
        coupon.id,
    )

    result = await (
        loyalty_coupon_service.repository.get_by_id(
            coupon.id,
        )
    )

    assert result is None

    print(
        "Unused coupon deletion: OK"
    )


@pytest.mark.asyncio
async def test_delete_used_coupon_rejected(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Used coupons must be retained for audit/history.
    """

    user, account = await create_customer_with_account(
        db_session,
    )

    payment = await create_test_payment_transaction(
        db_session,
        customer_id=user.id,
    )

    coupon = await create_test_coupon(
        db_session,
        loyalty_account_id=account.id,
        status=CouponStatus.USED,
        is_active=False,
        used_at=datetime.now(timezone.utc),
        used_payment_transaction_id=payment.id,
    )

    await db_session.commit()

    with pytest.raises(
        BadRequestException,
        match="Used loyalty coupons cannot be deleted",
    ):
        await loyalty_coupon_service.delete_coupon(
            coupon.id,
        )

    print(
        "Used coupon deletion correctly rejected: OK"
    )


# ==========================================================
# Complete Service Lifecycle
# ==========================================================


@pytest.mark.asyncio
async def test_loyalty_coupon_service_complete_lifecycle(
    db_session: AsyncSession,
    loyalty_coupon_service: LoyaltyCouponService,
):
    """
    Complete LoyaltyCouponService lifecycle test.

    Workflow
    --------

        User
          ↓
        LoyaltyAccount
          ↓
        Create Coupon
          ↓
        Retrieve Coupon
          ↓
        Validate Coupon
          ↓
        Use Coupon
          ↓
        Verify USED state
    """

    user, account = await create_customer_with_account(
        db_session,
    )

    print(
        f"Test customer created: {user.id}"
    )

    # ------------------------------------------------------
    # Create
    # ------------------------------------------------------

    coupon = await loyalty_coupon_service.create_coupon(
        customer_id=user.id,
        coupon_type=(
            CouponType.FIXED_AMOUNT_DISCOUNT
        ),
        value=Decimal("200.00"),
        description="Complete lifecycle coupon",
    )

    assert coupon.id is not None

    print(
        "Coupon creation through service: OK"
    )

    # ------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------

    retrieved = (
        await loyalty_coupon_service.get_coupon(
            coupon.id,
        )
    )

    assert retrieved.id == coupon.id

    print(
        "Coupon retrieval through service: OK"
    )

    # ------------------------------------------------------
    # Validate
    # ------------------------------------------------------

    validated = (
        await loyalty_coupon_service.validate_coupon(
            customer_id=user.id,
            coupon_code=coupon.coupon_code,
        )
    )

    assert validated.id == coupon.id
    assert validated.status == CouponStatus.ACTIVE

    print(
        "Coupon validation through service: OK"
    )

    # ------------------------------------------------------
    # Use
    # ------------------------------------------------------

    payment = await create_test_payment_transaction(
        db_session,
        customer_id=user.id,
    )

    used = await loyalty_coupon_service.use_coupon(
        customer_id=user.id,
        coupon_code=coupon.coupon_code,
        payment_transaction_id=payment.id,
    )

    assert used.status == CouponStatus.USED
    assert used.is_active is False
    assert used.used_at is not None
    assert used.used_payment_transaction_id is not None

    print(
        "Coupon usage through service: OK"
    )

    # ------------------------------------------------------
    # Final verification
    # ------------------------------------------------------

    final = (
        await loyalty_coupon_service.get_coupon(
            coupon.id,
        )
    )

    assert final.status == CouponStatus.USED
    assert final.is_active is False
    assert final.used_payment_transaction_id == payment.id

    print(
        "Final coupon verification: OK"
    )

    print(
        "\n"
        "====================================================\n"
        "Loyalty Coupon Service Integration Test\n"
        "POSTGRESQL -> LOYALTY ACCOUNT\n"
        "-> COUPON SERVICE -> COUPON REPOSITORY\n"
        "COMPLETE LIFECYCLE: PASSED\n"
        "===================================================="
    )