"""
Integration tests for LoyaltyReferralRepository.

These tests verify:

PostgreSQL
    ↓
User
    ↓
LoyaltyReferral
    ↓
LoyaltyReferralRepository

Business rules are intentionally NOT tested here.
Those belong in LoyaltyReferralService.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

from app.models.enums import ReferralStatus
from app.models.loyalty_referral import LoyaltyReferral
from app.models.user import User

from app.repositories.loyalty_referral_repository import (
    LoyaltyReferralRepository,
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


def unique_value(
    prefix: str,
) -> str:
    """
    Generate a unique value so repeated integration test
    executions do not collide with persisted test data.
    """

    return (
        f"{prefix}-"
        f"{uuid4().hex[:12].upper()}"
    )


async def create_test_user(
    db: AsyncSession,
    *,
    email: str | None = None,
) -> User:
    """
    Create a minimal test customer.
    """

    user = User(
        first_name="Referral",
        last_name="IntegrationTest",
        email=email
        or f"{unique_value('customer').lower()}@test.local",
        phone_number=unique_value("2547"),
        password_hash="integration-test-password",
        is_active=True,
    )

    db.add(user)

    await db.flush()
    await db.refresh(user)

    return user


# ==========================================================
# Integration Test
# ==========================================================


@pytest.mark.asyncio
async def test_loyalty_referral_repository_complete_integration(
    db_session: AsyncSession,
) -> None:
    """
    Complete PostgreSQL integration test for
    LoyaltyReferralRepository.
    """

    repository = LoyaltyReferralRepository(
        db=db_session,
    )

    # ======================================================
    # Create Test Customers
    # ======================================================

    referrer = await create_test_user(
        db_session,
    )

    referred = await create_test_user(
        db_session,
    )

    assert referrer.id is not None
    assert referred.id is not None
    assert referrer.id != referred.id

    print(
        f"Test referrer created: {referrer.id}"
    )

    print(
        f"Test referred customer created: "
        f"{referred.id}"
    )

    # ======================================================
    # Create Referral
    # ======================================================

    referral_code = unique_value(
        "REF",
    )

    referral = LoyaltyReferral(
        referrer_id=referrer.id,
        referred_id=referred.id,
        referral_code=referral_code,
        status=ReferralStatus.PENDING,
        reward_points=100,
        notes="Referral repository integration test",
    )

    created = await repository.save(
        referral,
    )

    assert created.id is not None
    assert created.referrer_id == referrer.id
    assert created.referred_id == referred.id
    assert created.referral_code == referral_code
    assert created.status == ReferralStatus.PENDING
    assert created.reward_points == 100

    print("Referral creation: OK")

    # ======================================================
    # Lookup By ID
    # ======================================================

    found = await repository.get_by_id(
        created.id,
    )

    assert found is not None
    assert found.id == created.id
    assert found.referrer_id == referrer.id
    assert found.referred_id == referred.id

    print("Referral lookup: OK")

    # ======================================================
    # Lookup By Referral Code
    # ======================================================

    found_by_code = await repository.get_by_code(
        referral_code,
    )

    assert found_by_code is not None
    assert found_by_code.id == created.id
    assert found_by_code.referral_code == referral_code

    print("Referral code lookup: OK")

    # ======================================================
    # Referral Code Existence
    # ======================================================

    code_exists = await repository.exists_by_code(
        referral_code,
    )

    assert code_exists is True

    missing_code_exists = (
        await repository.exists_by_code(
            unique_value("MISSING"),
        )
    )

    assert missing_code_exists is False

    print("Referral code existence check: OK")

    # ======================================================
    # Get By Referrer
    # ======================================================

    referrer_referrals = (
        await repository.get_by_referrer(
            referrer.id,
        )
    )

    assert any(
        item.id == created.id
        for item in referrer_referrals
    )

    print("Referrer referral retrieval: OK")

    # ======================================================
    # Get By Referred Customer
    # ======================================================

    referred_referrals = (
        await repository.get_by_referred_customer(
            referred.id,
        )
    )

    assert any(
        item.id == created.id
        for item in referred_referrals
    )

    print("Referred customer retrieval: OK")

    # ======================================================
    # Customer Referral History
    # ======================================================

    referrer_history = (
        await repository.get_customer_referrals(
            referrer.id,
        )
    )

    assert any(
        item.id == created.id
        for item in referrer_history
    )

    referred_history = (
        await repository.get_customer_referrals(
            referred.id,
        )
    )

    assert any(
        item.id == created.id
        for item in referred_history
    )

    print("Customer referral history: OK")

    # ======================================================
    # Get By Status - PENDING
    # ======================================================

    pending = await repository.get_by_status(
        ReferralStatus.PENDING,
    )

    assert any(
        item.id == created.id
        for item in pending
    )

    print("Referral status filtering: OK")

    # ======================================================
    # Pending Shortcut
    # ======================================================

    pending_shortcut = (
        await repository.get_pending()
    )

    assert any(
        item.id == created.id
        for item in pending_shortcut
    )

    print("Pending referral retrieval: OK")

    # ======================================================
    # Active Referral
    # ======================================================

    active = await repository.get_active_by_id(
        created.id,
    )

    assert active is not None
    assert active.id == created.id
    assert active.status == ReferralStatus.PENDING

    print("Active referral lookup: OK")

    # ======================================================
    # Pending Referral For Referred Customer
    # ======================================================

    pending_for_customer = (
        await repository.get_pending_for_referred_customer(
            referred.id,
        )
    )

    assert pending_for_customer is not None
    assert pending_for_customer.id == created.id

    print(
        "Pending referred-customer lookup: OK"
    )

    # ======================================================
    # Referrer + Referred Pair Lookup
    # ======================================================

    pair_result = (
        await repository.get_by_referrer_and_referred(
            referrer.id,
            referred.id,
        )
    )

    assert pair_result is not None
    assert pair_result.id == created.id

    print(
        "Referrer/referred pair lookup: OK"
    )

    # ======================================================
    # Count By Referrer
    # ======================================================

    referrer_count = (
        await repository.count_by_referrer(
            referrer.id,
        )
    )

    assert referrer_count >= 1

    print("Referrer count: OK")

    # ======================================================
    # Count By Referred Customer
    # ======================================================

    referred_count = (
        await repository.count_by_referred_customer(
            referred.id,
        )
    )

    assert referred_count >= 1

    print("Referred customer count: OK")

    # ======================================================
    # Count Customer Referrals
    # ======================================================

    customer_count = (
        await repository.count_customer_referrals(
            referrer.id,
        )
    )

    assert customer_count >= 1

    print("Customer referral count: OK")

    # ======================================================
    # Count By Status
    # ======================================================

    pending_count = (
        await repository.count_by_status(
            ReferralStatus.PENDING,
        )
    )

    assert pending_count >= 1

    print("Status count: OK")

    # ======================================================
    # Count All
    # ======================================================

    total_count = await repository.count_all()

    assert total_count >= 1

    print("Total referral count: OK")

    # ======================================================
    # Get All
    # ======================================================

    all_referrals = await repository.get_all()

    assert any(
        item.id == created.id
        for item in all_referrals
    )

    print("Get all referrals: OK")

    # ======================================================
    # Update → QUALIFIED
    # ======================================================

    created.status = ReferralStatus.QUALIFIED
    created.qualified_at = datetime.now(
        timezone.utc,
    )

    updated = await repository.update(
        created,
    )

    assert updated.status == ReferralStatus.QUALIFIED
    assert updated.qualified_at is not None

    print("Referral update → QUALIFIED: OK")

    # ======================================================
    # Qualified Filtering
    # ======================================================

    qualified = (
        await repository.get_by_status(
            ReferralStatus.QUALIFIED,
        )
    )

    assert any(
        item.id == created.id
        for item in qualified
    )

    qualified_shortcut = (
        await repository.get_qualified()
    )

    assert any(
        item.id == created.id
        for item in qualified_shortcut
    )

    print("Qualified referral filtering: OK")

    # ======================================================
    # Active Qualified Referral
    # ======================================================

    qualified_active = (
        await repository.get_active_by_id(
            created.id,
        )
    )

    assert qualified_active is not None
    assert (
        qualified_active.status
        == ReferralStatus.QUALIFIED
    )

    print(
        "Qualified referral active lookup: OK"
    )

    # ======================================================
    # Update → REWARDED
    # ======================================================

    created.status = ReferralStatus.REWARDED
    created.rewarded_at = datetime.now(
        timezone.utc,
    )

    updated = await repository.update(
        created,
    )

    assert updated.status == ReferralStatus.REWARDED
    assert updated.rewarded_at is not None

    print("Referral update → REWARDED: OK")

    # ======================================================
    # Rewarded Filtering
    # ======================================================

    rewarded = (
        await repository.get_by_status(
            ReferralStatus.REWARDED,
        )
    )

    assert any(
        item.id == created.id
        for item in rewarded
    )

    rewarded_shortcut = (
        await repository.get_rewarded()
    )

    assert any(
        item.id == created.id
        for item in rewarded_shortcut
    )

    print("Rewarded referral filtering: OK")

    # ======================================================
    # Rewarded Referral Is No Longer Active
    # ======================================================

    rewarded_active = (
        await repository.get_active_by_id(
            created.id,
        )
    )

    assert rewarded_active is None

    print(
        "Rewarded referral inactive check: OK"
    )

    # ======================================================
    # Create Second Referral
    # ======================================================

    second_referral = LoyaltyReferral(
        referrer_id=referrer.id,
        referred_id=referred.id,
        referral_code=unique_value("REF"),
        status=ReferralStatus.PENDING,
        reward_points=50,
        notes="Second referral lifecycle test",
    )

    second_referral = await repository.save(
        second_referral,
    )

    assert second_referral.id is not None

    print("Second referral creation: OK")

    # ======================================================
    # Update Second Referral → CANCELLED
    # ======================================================

    second_referral.status = (
        ReferralStatus.CANCELLED
    )

    second_referral.cancelled_at = datetime.now(
        timezone.utc,
    )

    updated_second = await repository.update(
        second_referral,
    )

    assert (
        updated_second.status
        == ReferralStatus.CANCELLED
    )

    assert (
        updated_second.cancelled_at
        is not None
    )

    print("Referral update → CANCELLED: OK")

    # ======================================================
    # Cancelled Filtering
    # ======================================================

    cancelled = (
        await repository.get_by_status(
            ReferralStatus.CANCELLED,
        )
    )

    assert any(
        item.id == second_referral.id
        for item in cancelled
    )

    cancelled_shortcut = (
        await repository.get_cancelled()
    )

    assert any(
        item.id == second_referral.id
        for item in cancelled_shortcut
    )

    print("Cancelled referral filtering: OK")

    # ======================================================
    # Final Verification
    # ======================================================

    final_rewarded = await repository.get_by_id(
        created.id,
    )

    assert final_rewarded is not None
    assert (
        final_rewarded.status
        == ReferralStatus.REWARDED
    )
    assert final_rewarded.reward_points == 100

    final_cancelled = await repository.get_by_id(
        second_referral.id,
    )

    assert final_cancelled is not None
    assert (
        final_cancelled.status
        == ReferralStatus.CANCELLED
    )
    assert final_cancelled.reward_points == 50

    print("Final referral verification: OK")

    # ======================================================
    # Delete Second Referral
    # ======================================================

    await repository.delete(
        second_referral,
    )

    deleted = await repository.get_by_id(
        second_referral.id,
    )

    assert deleted is None

    print("Referral deletion: OK")

    # ======================================================
    # Commit
    # ======================================================

    await db_session.commit()

    print(
        "\n"
        "====================================================\n"
        "Loyalty Referral Repository Integration Test\n"
        "POSTGRESQL -> USERS -> LOYALTY REFERRALS\n"
        "-> REFERRAL REPOSITORY\n"
        "INTEGRATION TEST: PASSED\n"
        "===================================================="
    )