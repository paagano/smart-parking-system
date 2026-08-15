"""
Loyalty Referral API Integration Tests.

These tests exercise the real SmartPark Loyalty Referral API
through the FastAPI application.

Architecture under test
-----------------------

    HTTP Request
         |
         v
    FastAPI Referral Endpoint
         |
         v
    Authentication Dependency
         |
         v
    LoyaltyReferralService
         |
         +-------------------------+
         |                         |
         v                         v
    LoyaltyReferralRepository   LoyaltyService
         |                         |
         v                         v
    PostgreSQL               LoyaltyRepository
                                   |
                                   v
                              PostgreSQL


The tests use:

- Real FastAPI application
- Real PostgreSQL test database
- Real SQLAlchemy AsyncSession
- Real LoyaltyReferralService
- Real LoyaltyReferralRepository
- Real LoyaltyService
- Real LoyaltyRepository
- Real LoyaltyReferral model
- Real LoyaltyAccount model
- Real User model
- Real HTTP requests through httpx.AsyncClient

The tests do NOT:

- call the production database
- call the login API
- use mocked services
- use mocked repositories
- use mocked HTTP endpoints

Authentication
--------------

The authenticated-user dependency is overridden with a real
User created in the PostgreSQL test database.

This keeps the API integration test focused on the Referral
API while still exercising the actual FastAPI dependency
chain.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.api.dependencies.auth import (
    get_current_active_user,
)

from app.config import settings

from app.database.dependencies import (
    get_db as dependencies_get_db,
)

from app.database.session import (
    get_db as session_get_db,
)

from app.main import app

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

    Uses TEST_DATABASE_URL.

    The production/development database is never used.
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
# Test User Factory
# ==========================================================


async def create_test_user(
    db: AsyncSession,
    *,
    prefix: str = "referral.api",
    is_active: bool = True,
) -> User:
    """
    Create a unique real test customer.
    """

    unique_id = uuid4().hex[:10].lower()

    user = User(
        first_name="Referral",
        last_name="API Test",
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
    Create a real loyalty account for a test customer.
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
# API Client Fixture
# ==========================================================


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession,
):
    """
    Create an asynchronous HTTP client against the real
    FastAPI application.

    The application database dependencies are overridden
    so all API operations use the real PostgreSQL test
    session.

    The authenticated active user dependency is overridden
    with a real User created in PostgreSQL.
    """

    test_user = await create_test_user(
        db_session,
        prefix="referral.api.authenticated",
    )

    async def override_get_db():
        """
        Use the test PostgreSQL session for API requests.
        """

        yield db_session

    async def override_current_active_user():
        """
        Use the real test user as the authenticated customer.
        """

        return test_user

    # ------------------------------------------------------
    # Override database dependencies
    # ------------------------------------------------------

    app.dependency_overrides[
        dependencies_get_db
    ] = override_get_db

    app.dependency_overrides[
        session_get_db
    ] = override_get_db

    # ------------------------------------------------------
    # Override authentication
    # ------------------------------------------------------

    app.dependency_overrides[
        get_current_active_user
    ] = override_current_active_user

    transport = httpx.ASGITransport(
        app=app,
    )

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:

        yield client, test_user

    # ------------------------------------------------------
    # Always remove dependency overrides
    # ------------------------------------------------------

    app.dependency_overrides.clear()


# ==========================================================
# Helper - Create Referral Through API
# ==========================================================


async def create_referral_through_api(
    client: httpx.AsyncClient,
    *,
    referred_id: int,
    reward_points: int = 100,
    prefix: str = "REF-API",
) -> tuple[dict, str]:
    """
    Create a referral through the actual HTTP API.

    Returns:

        (
            response JSON,
            referral_code,
        )
    """

    referral_code = (
        f"{prefix}-{uuid4().hex[:12].upper()}"
    )

    response = await client.post(
        "/loyalty/referrals",
        json={
            "referral_code": referral_code,
            "referred_id": referred_id,
            "reward_points": reward_points,
            "notes": "Referral API integration test",
        },
    )

    assert response.status_code == 201, response.text

    data = response.json()

    return data, referral_code


# ==========================================================
# Complete Referral API Lifecycle
# ==========================================================


@pytest.mark.asyncio
async def test_loyalty_referral_api_complete_integration(
    db_session: AsyncSession,
    api_client,
):
    """
    Exercise the complete Loyalty Referral API lifecycle.

    Workflow
    --------

        POST /loyalty/referrals
                    |
                    v
                 PENDING
                    |
                    +--------------------------+
                    |                          |
                    v                          v
        GET /referrals/{id}         GET /referrals/code/{code}
                    |
                    v
        POST /referrals/validate
                    |
                    v
        POST /referrals/{id}/qualify
                    |
                    v
                QUALIFIED
                    |
                    v
        POST /referrals/{id}/reward
                    |
                    v
                 REWARDED
                    |
                    v
        GET /referrals/{id}/status

    A second referral is also created to verify:

        PENDING
           |
           v
        ACTIVE
           |
           v
        CANCELLED
    """

    client, authenticated_user = api_client

    # ======================================================
    # 1. Create referred customer
    # ======================================================

    referred_user = await create_test_user(
        db_session,
        prefix="referral.api.referred",
    )

    # ------------------------------------------------------
    # Create loyalty accounts.
    #
    # The referral reward ultimately awards points to the
    # referrer through LoyaltyService.
    # ------------------------------------------------------

    referrer_account = (
        await create_test_loyalty_account(
            db_session,
            customer_id=authenticated_user.id,
            points_balance=0,
            lifetime_points=0,
            tier=LoyaltyTier.BRONZE,
        )
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=referred_user.id,
    )

    await db_session.flush()

    # ======================================================
    # 2. Create Referral
    # ======================================================

    referral_data, referral_code = (
        await create_referral_through_api(
            client,
            referred_id=referred_user.id,
            reward_points=100,
        )
    )

    referral_id = referral_data["id"]

    assert referral_id > 0

    assert (
        referral_data["referrer_id"]
        == authenticated_user.id
    )

    assert (
        referral_data["referred_id"]
        == referred_user.id
    )

    assert (
        referral_data["referral_code"]
        == referral_code
    )

    assert (
        referral_data["status"]
        == ReferralStatus.PENDING.value
    )

    assert (
        referral_data["reward_points"]
        == 100
    )

    assert (
        referral_data["qualified_at"]
        is None
    )

    assert (
        referral_data["rewarded_at"]
        is None
    )

    assert (
        referral_data["cancelled_at"]
        is None
    )

    print(
        "POST /loyalty/referrals: OK"
    )

    # ======================================================
    # 3. Verify Referral persisted in PostgreSQL
    # ======================================================

    result = await db_session.execute(
        select(
            LoyaltyReferral,
        ).where(
            LoyaltyReferral.id == referral_id,
        )
    )

    persisted_referral = (
        result.scalar_one_or_none()
    )

    assert persisted_referral is not None

    assert (
        persisted_referral.referrer_id
        == authenticated_user.id
    )

    assert (
        persisted_referral.referred_id
        == referred_user.id
    )

    assert (
        persisted_referral.referral_code
        == referral_code
    )

    assert (
        persisted_referral.status
        == ReferralStatus.PENDING
    )

    print(
        "PostgreSQL referral persistence: OK"
    )

    # ======================================================
    # 4. GET Referral By ID
    # ======================================================

    response = await client.get(
        f"/loyalty/referrals/{referral_id}",
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["id"] == referral_id

    assert (
        data["referral_code"]
        == referral_code
    )

    assert (
        data["status"]
        == ReferralStatus.PENDING.value
    )

    print(
        "GET /loyalty/referrals/{id}: OK"
    )

    # ======================================================
    # 5. GET Referral By Code
    # ======================================================

    response = await client.get(
        f"/loyalty/referrals/code/{referral_code}",
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["id"] == referral_id

    assert (
        data["referral_code"]
        == referral_code
    )

    assert (
        data["referrer_id"]
        == authenticated_user.id
    )

    print(
        "GET /loyalty/referrals/code/{code}: OK"
    )

    # ======================================================
    # 6. Validate Referral As Referred Customer
    #
    # The authenticated customer is temporarily changed
    # from the referrer to the referred customer.
    # ======================================================

    original_active_user_override = (
        app.dependency_overrides[
            get_current_active_user
        ]
    )

    async def override_referred_customer():
        return referred_user

    app.dependency_overrides[
        get_current_active_user
    ] = override_referred_customer

    try:

        response = await client.post(
            "/loyalty/referrals/validate",
            json={
                "referral_code": referral_code,
            },
        )

        assert response.status_code == 200, (
            response.text
        )

        data = response.json()

        assert data["valid"] is True

        assert (
            data["referral_code_exists"]
            is True
        )

        assert (
            data["referral_is_active"]
            is True
        )

        assert (
            data["customer_is_eligible"]
            is True
        )

        assert (
            data["referral"]["id"]
            == referral_id
        )

        assert (
            data["referral"]["status"]
            == ReferralStatus.PENDING.value
        )

        assert data["reason"] is None

        print(
            "POST /loyalty/referrals/validate "
            "successful validation: OK"
        )

    finally:

        app.dependency_overrides[
            get_current_active_user
        ] = original_active_user_override

    # ======================================================
    # 7. Validate Own Referral Code
    #
    # Restore the original authenticated referrer.
    # The referrer must not be able to use their own code.
    # ======================================================

    response = await client.post(
        "/loyalty/referrals/validate",
        json={
            "referral_code": referral_code,
        },
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["valid"] is False

    assert (
        data["referral_code_exists"]
        is True
    )

    assert (
        data["referral_is_active"]
        is True
    )

    assert (
        data["customer_is_eligible"]
        is False
    )

    assert (
        data["reason"]
        == "A customer cannot use their own referral code."
    )

    print(
        "POST /loyalty/referrals/validate "
        "self-referral rejection: OK"
    )

    # ======================================================
    # 8. GET Active Referral
    #
    # Referral is still PENDING and therefore active.
    # ======================================================

    response = await client.get(
        f"/loyalty/referrals/{referral_id}/active",
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["id"] == referral_id

    assert (
        data["status"]
        == ReferralStatus.PENDING.value
    )

    print(
        "GET /loyalty/referrals/{id}/active: OK"
    )

    # ======================================================
    # 9. Qualify Referral
    # ======================================================

    response = await client.post(
        f"/loyalty/referrals/{referral_id}/qualify",
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["qualified"] is True

    assert (
        data["referral"]["id"]
        == referral_id
    )

    assert (
        data["referral"]["status"]
        == ReferralStatus.QUALIFIED.value
    )

    assert (
        data["qualified_at"]
        is not None
    )

    assert (
        data["referral"]["qualified_at"]
        is not None
    )

    print(
        "POST /loyalty/referrals/{id}/qualify: OK"
    )

    # ======================================================
    # 10. GET Active Referral After Qualification
    # ======================================================

    response = await client.get(
        f"/loyalty/referrals/{referral_id}/active",
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["id"] == referral_id

    assert (
        data["status"]
        == ReferralStatus.QUALIFIED.value
    )

    print(
        "Active referral after qualification: OK"
    )

    # ======================================================
    # 11. Reward Referral
    # ======================================================

    response = await client.post(
        f"/loyalty/referrals/{referral_id}/reward",
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["rewarded"] is True

    assert (
        data["referral"]["id"]
        == referral_id
    )

    assert (
        data["referral"]["status"]
        == ReferralStatus.REWARDED.value
    )

    assert (
        data["referral"]["reward_points"]
        == 100
    )

    assert (
        data["rewarded_at"]
        is not None
    )

    assert (
        data["referral"]["rewarded_at"]
        is not None
    )

    print(
        "POST /loyalty/referrals/{id}/reward: OK"
    )

    # ======================================================
    # 12. Verify Loyalty Account Was Rewarded
    # ======================================================

    await db_session.refresh(
        referrer_account,
    )

    assert (
        referrer_account.points_balance
        == 100
    )

    assert (
        referrer_account.lifetime_points
        == 100
    )

    print(
        "Loyalty account reward: OK"
    )

    # ======================================================
    # 13. Verify Loyalty Ledger
    # ======================================================

    result = await db_session.execute(
        select(
            LoyaltyPointTransaction,
        ).where(
            LoyaltyPointTransaction.loyalty_account_id
            == referrer_account.id,
            LoyaltyPointTransaction.reference_type
            == "LOYALTY_REFERRAL",
            LoyaltyPointTransaction.reference_id
            == referral_id,
        )
    )

    transaction = (
        result.scalars().first()
    )

    assert transaction is not None

    assert transaction.points == 100

    assert (
        transaction.balance_after
        == 100
    )

    assert transaction.transaction_type in {
        LoyaltyPointTransactionType.REFERRAL_BONUS,
        LoyaltyPointTransactionType.EARN,
    }

    print(
        "Loyalty referral ledger transaction: OK"
    )

    # ======================================================
    # 14. GET Referral Status
    # ======================================================

    response = await client.get(
        f"/loyalty/referrals/{referral_id}/status",
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["id"] == referral_id

    assert (
        data["status"]
        == ReferralStatus.REWARDED.value
    )

    print(
        "GET /loyalty/referrals/{id}/status: OK"
    )

    # ======================================================
    # 15. Verify Rewarded Referral Is No Longer Active
    # ======================================================

    response = await client.get(
        f"/loyalty/referrals/{referral_id}/active",
    )

    assert response.status_code in {
        404,
    }, response.text

    print(
        "Rewarded referral no longer active: OK"
    )

    # ======================================================
    # 16. Verify Final PostgreSQL State
    # ======================================================

    await db_session.refresh(
        persisted_referral,
    )

    assert (
        persisted_referral.status
        == ReferralStatus.REWARDED
    )

    assert (
        persisted_referral.rewarded_at
        is not None
    )

    assert (
        persisted_referral.cancelled_at
        is None
    )

    print(
        "Final referral verification: OK"
    )

    print(
        "\n"
        "====================================================\n"
        "Loyalty Referral API Integration Test\n"
        "HTTP -> FASTAPI -> SERVICE -> REPOSITORY\n"
        "-> POSTGRESQL -> LOYALTY ACCOUNT -> LEDGER\n"
        "INTEGRATION TEST: PASSED\n"
        "===================================================="
    )


# ==========================================================
# Cancellation API Lifecycle
# ==========================================================


@pytest.mark.asyncio
async def test_loyalty_referral_api_cancellation(
    db_session: AsyncSession,
    api_client,
):
    """
    Verify the Referral cancellation API lifecycle.

    Workflow:

        POST /loyalty/referrals
                    |
                    v
                 PENDING
                    |
                    v
        GET /referrals/{id}/active
                    |
                    v
        POST /referrals/{id}/cancel
                    |
                    v
                CANCELLED
                    |
                    v
        GET /referrals/{id}/status
    """

    client, authenticated_user = api_client

    # ======================================================
    # Create referred customer
    # ======================================================

    referred_user = await create_test_user(
        db_session,
        prefix="referral.api.cancel",
    )

    # ======================================================
    # Create referral
    # ======================================================

    referral_data, referral_code = (
        await create_referral_through_api(
            client,
            referred_id=referred_user.id,
            reward_points=100,
            prefix="REF-CANCEL",
        )
    )

    referral_id = referral_data["id"]

    assert (
        referral_data["status"]
        == ReferralStatus.PENDING.value
    )

    # ======================================================
    # Verify Active
    # ======================================================

    response = await client.get(
        f"/loyalty/referrals/{referral_id}/active",
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert (
        data["status"]
        == ReferralStatus.PENDING.value
    )

    print(
        "Cancellation lifecycle - active: OK"
    )

    # ======================================================
    # Cancel Referral
    # ======================================================

    response = await client.post(
        f"/loyalty/referrals/{referral_id}/cancel",
        json={
            "referral_id": referral_id,
            "reason": (
                "API integration cancellation test"
            ),
        },
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["cancelled"] is True

    assert (
        data["referral"]["id"]
        == referral_id
    )

    assert (
        data["referral"]["status"]
        == ReferralStatus.CANCELLED.value
    )

    assert (
        data["cancelled_at"]
        is not None
    )

    assert (
        data["referral"]["cancelled_at"]
        is not None
    )

    print(
        "POST /loyalty/referrals/{id}/cancel: OK"
    )

    # ======================================================
    # Verify Status
    # ======================================================

    response = await client.get(
        f"/loyalty/referrals/{referral_id}/status",
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert (
        data["status"]
        == ReferralStatus.CANCELLED.value
    )

    print(
        "Cancellation status verification: OK"
    )

    # ======================================================
    # Verify No Longer Active
    # ======================================================

    response = await client.get(
        f"/loyalty/referrals/{referral_id}/active",
    )

    assert response.status_code == 404, response.text

    print(
        "Cancelled referral no longer active: OK"
    )

    # ======================================================
    # Verify PostgreSQL
    # ======================================================

    result = await db_session.execute(
        select(
            LoyaltyReferral,
        ).where(
            LoyaltyReferral.id == referral_id,
        )
    )

    referral = (
        result.scalar_one_or_none()
    )

    assert referral is not None

    assert (
        referral.referrer_id
        == authenticated_user.id
    )

    assert (
        referral.referred_id
        == referred_user.id
    )

    assert (
        referral.referral_code
        == referral_code
    )

    assert (
        referral.status
        == ReferralStatus.CANCELLED
    )

    assert (
        referral.cancelled_at
        is not None
    )

    print(
        "Cancellation PostgreSQL verification: OK"
    )


# ==========================================================
# Referral API Validation - Invalid Code
# ==========================================================


@pytest.mark.asyncio
async def test_loyalty_referral_api_validation_invalid_code(
    api_client,
):
    """
    Verify that a non-existent referral code is rejected
    by the validation endpoint.
    """

    client, _ = api_client

    invalid_code = (
        f"REF-NOT-FOUND-{uuid4().hex[:12].upper()}"
    )

    response = await client.post(
        "/loyalty/referrals/validate",
        json={
            "referral_code": invalid_code,
        },
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["valid"] is False

    assert (
        data["referral"]
        is None
    )

    assert (
        data["referral_code_exists"]
        is False
    )

    assert (
        data["referral_is_active"]
        is False
    )

    assert (
        data["customer_is_eligible"]
        is False
    )

    assert data["reason"] is not None

    print(
        "Invalid referral code correctly rejected: OK"
    )


# ==========================================================
# Referral API Validation - Duplicate Code
# ==========================================================


@pytest.mark.asyncio
async def test_loyalty_referral_api_duplicate_code_rejected(
    db_session: AsyncSession,
    api_client,
):
    """
    Verify that duplicate referral codes are rejected
    through the HTTP API.
    """

    client, _ = api_client

    referred_user = await create_test_user(
        db_session,
        prefix="referral.api.duplicate",
    )

    referral_code = (
        f"REF-DUPLICATE-{uuid4().hex[:12].upper()}"
    )

    # ------------------------------------------------------
    # First referral
    # ------------------------------------------------------

    response = await client.post(
        "/loyalty/referrals",
        json={
            "referral_code": referral_code,
            "referred_id": referred_user.id,
            "reward_points": 100,
            "notes": "First referral",
        },
    )

    assert response.status_code == 201, response.text

    first = response.json()

    assert (
        first["referral_code"]
        == referral_code
    )

    # ------------------------------------------------------
    # Second referral with same code
    #
    # Use another referred customer because the service
    # also rejects multiple pending referrals for the same
    # referred customer.
    # ------------------------------------------------------

    second_referred_user = await create_test_user(
        db_session,
        prefix="referral.api.duplicate.second",
    )

    response = await client.post(
        "/loyalty/referrals",
        json={
            "referral_code": referral_code,
            "referred_id": second_referred_user.id,
            "reward_points": 100,
            "notes": "Duplicate referral code test",
        },
    )

    assert response.status_code == 400, response.text

    print(
        "Duplicate referral code correctly rejected: OK"
    )


# ==========================================================
# Referral API Self-Referral Rejection
# ==========================================================


@pytest.mark.asyncio
async def test_loyalty_referral_api_self_referral_rejected(
    api_client,
):
    """
    Verify that a customer cannot refer themselves.
    """

    client, authenticated_user = api_client

    referral_code = (
        f"REF-SELF-{uuid4().hex[:12].upper()}"
    )

    response = await client.post(
        "/loyalty/referrals",
        json={
            "referral_code": referral_code,
            "referred_id": authenticated_user.id,
            "reward_points": 100,
            "notes": "Self referral rejection test",
        },
    )

    assert response.status_code == 400, response.text

    print(
        "Self-referral correctly rejected: OK"
    )


# ==========================================================
# Referral API Missing Customer Validation
# ==========================================================


@pytest.mark.asyncio
async def test_loyalty_referral_api_missing_customer_rejected(
    api_client,
):
    """
    Verify that referral creation rejects a non-existent
    referred customer.
    """

    client, _ = api_client

    nonexistent_customer_id = (
        999_999_999
    )

    referral_code = (
        f"REF-MISSING-{uuid4().hex[:12].upper()}"
    )

    response = await client.post(
        "/loyalty/referrals",
        json={
            "referral_code": referral_code,
            "referred_id": nonexistent_customer_id,
            "reward_points": 100,
            "notes": "Missing customer test",
        },
    )

    assert response.status_code == 404, response.text

    print(
        "Missing referred customer correctly rejected: OK"
    )