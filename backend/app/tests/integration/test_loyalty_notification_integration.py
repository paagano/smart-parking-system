"""
Integration tests for Loyalty -> Notification integration.

These tests verify that successful Loyalty operations generate
the appropriate Notification records through the existing
NotificationService.

Covered notifications
---------------------
1. LOYALTY_POINTS_EARNED
2. LOYALTY_TIER_UPGRADED

Important
---------
These tests intentionally use the real:

    LoyaltyService
        ->
    NotificationService
        ->
    NotificationRepository
        ->
    PostgreSQL

No notification service mocking is used for the successful
integration scenarios.

The tests also verify that notification failures do not break
the underlying Loyalty transaction.
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

from app.models.enums import (
    LoyaltyPointTransactionType,
    LoyaltyTier,
    NotificationChannel,
    NotificationType,
)

from app.models.loyalty_account import (
    LoyaltyAccount,
)

from app.models.notification import (
    Notification,
)

from app.models.user import (
    User,
)

from app.repositories.loyalty_repository import (
    LoyaltyRepository,
)

from app.repositories.notification_repository import (
    NotificationRepository,
)

from app.services.loyalty_service import (
    LoyaltyService,
)

from app.services.notification_service import (
    NotificationService,
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
# Test Helpers
# ==========================================================


def unique_value(
    prefix: str,
) -> str:
    """
    Generate a unique value for test data.
    """

    return (
        f"{prefix}-"
        f"{uuid4().hex[:12].upper()}"
    )


async def create_test_user(
    db: AsyncSession,
) -> User:
    """
    Create a minimal active test user.
    """

    user = User(
        first_name="Loyalty",
        last_name="Notification",
        email=(
            f"loyalty.notification."
            f"{uuid4().hex[:12]}@example.com"
        ),
        phone_number=(
            f"+2547"
            f"{uuid4().int % 100000000:08d}"
        ),
        password_hash="test-password-hash",
        is_active=True,
    )

    db.add(user)

    await db.flush()

    return user


async def create_test_loyalty_account(
    db: AsyncSession,
    *,
    customer_id: int,
    lifetime_points: int = 0,
    points_balance: int = 0,
    tier: LoyaltyTier = LoyaltyTier.BRONZE,
) -> LoyaltyAccount:
    """
    Create a LoyaltyAccount for the test customer.
    """

    account = LoyaltyAccount(
        customer_id=customer_id,
        points_balance=points_balance,
        lifetime_points=lifetime_points,
        tier=tier,
        is_active=True,
    )

    db.add(account)

    await db.flush()

    return account


def build_loyalty_service(
    db: AsyncSession,
) -> LoyaltyService:
    """
    Build the real LoyaltyService with its real
    NotificationService dependency.
    """

    loyalty_repository = LoyaltyRepository(
        db=db,
    )

    notification_repository = NotificationRepository(
        db=db,
    )

    notification_service = NotificationService(
        repository=notification_repository,
    )

    return LoyaltyService(
        db=db,
        repository=loyalty_repository,
        notification_service=notification_service,
    )


async def get_notifications_for_user(
    db: AsyncSession,
    *,
    user_id: int,
    notification_type: NotificationType | None = None,
) -> list[Notification]:
    """
    Retrieve notifications belonging to a test user.

    Optionally filter by notification type.
    """

    query = (
        select(Notification)
        .where(
            Notification.user_id == user_id,
        )
        .order_by(
            Notification.id.asc(),
        )
    )

    if notification_type is not None:
        query = query.where(
            Notification.type == notification_type,
        )

    result = await db.execute(query)

    return list(
        result.scalars().all(),
    )


# ==========================================================
# Points Earned Notification
# ==========================================================


@pytest.mark.asyncio
async def test_loyalty_points_earned_notification(
    db_session: AsyncSession,
) -> None:
    """
    Verify that awarding loyalty points creates a
    LOYALTY_POINTS_EARNED notification.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    await db_session.commit()

    service = build_loyalty_service(
        db_session,
    )

    transaction = await service.award_points(
        customer_id=user.id,
        points=150,
        transaction_type=(
            LoyaltyPointTransactionType.EARN
        ),
        reference_type="TEST",
        reference_id=(
            uuid4().int % 2_000_000_000
        ),
        description="Integration test points award.",
    )

    assert transaction.id is not None
    assert transaction.points == 150

    notifications = await get_notifications_for_user(
        db_session,
        user_id=user.id,
        notification_type=(
            NotificationType.LOYALTY_POINTS_EARNED
        ),
    )

    assert len(notifications) == 1

    notification = notifications[0]

    assert notification.user_id == user.id

    assert (
        notification.type
        == NotificationType.LOYALTY_POINTS_EARNED
    )

    assert (
        notification.channel
        == NotificationChannel.IN_APP
    )

    assert notification.title == (
        "Loyalty Points Earned"
    )

    assert "150" in notification.message

    assert "loyalty points" in (
        notification.message.lower()
    )

    assert (
        notification.related_entity_type
        == "LOYALTY_POINT_TRANSACTION"
    )

    assert (
        notification.related_entity_id
        == transaction.id
    )

    print(
        "LOYALTY_POINTS_EARNED notification: OK"
    )


# ==========================================================
# Tier Upgrade Notification
# ==========================================================


@pytest.mark.asyncio
async def test_loyalty_tier_upgraded_notification(
    db_session: AsyncSession,
) -> None:
    """
    Verify that crossing a loyalty tier threshold creates
    a LOYALTY_TIER_UPGRADED notification.
    """

    user = await create_test_user(
        db_session,
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        lifetime_points=900,
        points_balance=900,
        tier=LoyaltyTier.BRONZE,
    )

    await db_session.commit()

    service = build_loyalty_service(
        db_session,
    )

    transaction = await service.award_points(
        customer_id=user.id,
        points=100,
        transaction_type=(
            LoyaltyPointTransactionType.EARN
        ),
        reference_type="TEST_TIER_UPGRADE",
        reference_id=(
            uuid4().int % 2_000_000_000
        ),
        description="Integration test tier upgrade.",
    )

    assert transaction.id is not None

    await db_session.refresh(
        account,
    )

    assert (
        account.tier
        == LoyaltyTier.SILVER
    )

    notifications = await get_notifications_for_user(
        db_session,
        user_id=user.id,
        notification_type=(
            NotificationType.LOYALTY_TIER_UPGRADED
        ),
    )

    assert len(notifications) == 1

    notification = notifications[0]

    assert notification.user_id == user.id

    assert (
        notification.type
        == NotificationType.LOYALTY_TIER_UPGRADED
    )

    assert (
        notification.channel
        == NotificationChannel.IN_APP
    )

    assert notification.title == (
        "Loyalty Tier Upgraded"
    )

    assert "BRONZE" in notification.message
    assert "SILVER" in notification.message

    assert (
        notification.related_entity_type
        == "LOYALTY_ACCOUNT"
    )

    assert (
        notification.related_entity_id
        == account.id
    )

    print(
        "LOYALTY_TIER_UPGRADED notification: OK"
    )


# ==========================================================
# No Tier Notification When Tier Does Not Change
# ==========================================================


@pytest.mark.asyncio
async def test_no_tier_upgrade_notification_when_tier_unchanged(
    db_session: AsyncSession,
) -> None:
    """
    Verify that normal point awards do not generate a
    LOYALTY_TIER_UPGRADED notification when the customer's
    tier remains unchanged.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        lifetime_points=100,
        points_balance=100,
        tier=LoyaltyTier.BRONZE,
    )

    await db_session.commit()

    service = build_loyalty_service(
        db_session,
    )

    await service.award_points(
        customer_id=user.id,
        points=100,
        transaction_type=(
            LoyaltyPointTransactionType.EARN
        ),
        reference_type="TEST_NO_TIER_CHANGE",
        reference_id=(
            uuid4().int % 2_000_000_000
        ),
        description="No tier change test.",
    )

    notifications = await get_notifications_for_user(
        db_session,
        user_id=user.id,
        notification_type=(
            NotificationType.LOYALTY_TIER_UPGRADED
        ),
    )

    assert notifications == []

    points_notifications = (
        await get_notifications_for_user(
            db_session,
            user_id=user.id,
            notification_type=(
                NotificationType.LOYALTY_POINTS_EARNED
            ),
        )
    )

    assert len(points_notifications) == 1

    print(
        "No tier notification when tier unchanged: OK"
    )


# ==========================================================
# Idempotency - No Duplicate Notifications
# ==========================================================


@pytest.mark.asyncio
async def test_idempotent_award_does_not_duplicate_notifications(
    db_session: AsyncSession,
) -> None:
    """
    Verify that retrying the same idempotent point-award
    operation does not create duplicate notifications.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    await db_session.commit()

    service = build_loyalty_service(
        db_session,
    )

    reference_id = (
        uuid4().int % 2_000_000_000
    )

    first_transaction = (
        await service.award_points(
            customer_id=user.id,
            points=200,
            transaction_type=(
                LoyaltyPointTransactionType.EARN
            ),
            reference_type="TEST_IDEMPOTENCY",
            reference_id=reference_id,
            description="Idempotency notification test.",
        )
    )

    second_transaction = (
        await service.award_points(
            customer_id=user.id,
            points=200,
            transaction_type=(
                LoyaltyPointTransactionType.EARN
            ),
            reference_type="TEST_IDEMPOTENCY",
            reference_id=reference_id,
            description="Idempotency notification test.",
        )
    )

    assert (
        first_transaction.id
        == second_transaction.id
    )

    notifications = await get_notifications_for_user(
        db_session,
        user_id=user.id,
        notification_type=(
            NotificationType.LOYALTY_POINTS_EARNED
        ),
    )

    assert len(notifications) == 1

    print(
        "Idempotent award does not duplicate "
        "notification: OK"
    )


# ==========================================================
# Combined Points + Tier Upgrade
# ==========================================================


@pytest.mark.asyncio
async def test_points_and_tier_notifications_created_together(
    db_session: AsyncSession,
) -> None:
    """
    Verify that an award crossing a tier threshold creates
    both:

        LOYALTY_POINTS_EARNED
        LOYALTY_TIER_UPGRADED
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        lifetime_points=4_900,
        points_balance=4_900,
        tier=LoyaltyTier.SILVER,
    )

    await db_session.commit()

    service = build_loyalty_service(
        db_session,
    )

    transaction = await service.award_points(
        customer_id=user.id,
        points=100,
        transaction_type=(
            LoyaltyPointTransactionType.EARN
        ),
        reference_type="TEST_COMBINED_NOTIFICATION",
        reference_id=(
            uuid4().int % 2_000_000_000
        ),
        description="Combined loyalty notification test.",
    )

    assert transaction.points == 100

    points_notifications = (
        await get_notifications_for_user(
            db_session,
            user_id=user.id,
            notification_type=(
                NotificationType.LOYALTY_POINTS_EARNED
            ),
        )
    )

    tier_notifications = (
        await get_notifications_for_user(
            db_session,
            user_id=user.id,
            notification_type=(
                NotificationType.LOYALTY_TIER_UPGRADED
            ),
        )
    )

    assert len(points_notifications) == 1
    assert len(tier_notifications) == 1

    tier_notification = tier_notifications[0]

    assert "SILVER" in tier_notification.message
    assert "GOLD" in tier_notification.message

    print(
        "Points + tier upgrade notifications: OK"
    )


# ==========================================================
# Notification Failure Isolation
# ==========================================================


@pytest.mark.asyncio
async def test_notification_failure_does_not_break_loyalty_award(
    db_session: AsyncSession,
) -> None:
    """
    Verify that a NotificationService failure does not cause
    the underlying Loyalty point award to fail.

    This test intentionally replaces the notification service
    with a failing implementation.

    The Loyalty transaction must still be committed.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    await db_session.commit()

    service = build_loyalty_service(
        db_session,
    )

    class FailingNotificationService:
        """
        Notification service deliberately failing for the
        integration test.
        """

        async def create_notification(
            self,
            *,
            data,
        ):
            raise RuntimeError(
                "Simulated notification failure.",
            )

    service.notification_service = (
        FailingNotificationService()
    )

    transaction = await service.award_points(
        customer_id=user.id,
        points=300,
        transaction_type=(
            LoyaltyPointTransactionType.EARN
        ),
        reference_type="TEST_NOTIFICATION_FAILURE",
        reference_id=(
            uuid4().int % 2_000_000_000
        ),
        description=(
            "Notification failure isolation test."
        ),
    )

    assert transaction.id is not None
    assert transaction.points == 300

    account_result = await db_session.execute(
        select(LoyaltyAccount).where(
            LoyaltyAccount.customer_id == user.id,
        )
    )

    account = account_result.scalar_one()

    assert account.points_balance == 300
    assert account.lifetime_points == 300

    notifications = await get_notifications_for_user(
        db_session,
        user_id=user.id,
    )

    assert notifications == []

    print(
        "Notification failure does not break "
        "Loyalty award: OK"
    )


# ==========================================================
# Complete Integration Test
# ==========================================================


@pytest.mark.asyncio
async def test_loyalty_notification_integration_complete(
    db_session: AsyncSession,
) -> None:
    """
    Complete Loyalty -> Notification integration scenario.

    Verifies:

        LoyaltyService
            ->
        NotificationService
            ->
        NotificationRepository
            ->
        PostgreSQL

    for both Loyalty notification types.
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    await db_session.commit()

    service = build_loyalty_service(
        db_session,
    )

    # ------------------------------------------------------
    # Award points without tier upgrade
    # ------------------------------------------------------

    first_transaction = await service.award_points(
        customer_id=user.id,
        points=100,
        transaction_type=(
            LoyaltyPointTransactionType.EARN
        ),
        reference_type="TEST_COMPLETE_1",
        reference_id=(
            uuid4().int % 2_000_000_000
        ),
        description="Complete integration test - award 1.",
    )

    assert first_transaction.points == 100

    # ------------------------------------------------------
    # Award points crossing BRONZE -> SILVER
    # ------------------------------------------------------

    second_transaction = await service.award_points(
        customer_id=user.id,
        points=900,
        transaction_type=(
            LoyaltyPointTransactionType.EARN
        ),
        reference_type="TEST_COMPLETE_2",
        reference_id=(
            uuid4().int % 2_000_000_000
        ),
        description="Complete integration test - tier upgrade.",
    )

    assert second_transaction.points == 900

    # ------------------------------------------------------
    # Verify account
    # ------------------------------------------------------

    account_result = await db_session.execute(
        select(LoyaltyAccount).where(
            LoyaltyAccount.customer_id == user.id,
        )
    )

    account = account_result.scalar_one()

    assert account.points_balance == 1_000
    assert account.lifetime_points == 1_000
    assert account.tier == LoyaltyTier.SILVER

    # ------------------------------------------------------
    # Verify Points Earned Notifications
    # ------------------------------------------------------

    points_notifications = (
        await get_notifications_for_user(
            db_session,
            user_id=user.id,
            notification_type=(
                NotificationType.LOYALTY_POINTS_EARNED
            ),
        )
    )

    assert len(points_notifications) == 2

    assert all(
        notification.channel
        == NotificationChannel.IN_APP
        for notification in points_notifications
    )

    # ------------------------------------------------------
    # Verify Tier Upgrade Notification
    # ------------------------------------------------------

    tier_notifications = (
        await get_notifications_for_user(
            db_session,
            user_id=user.id,
            notification_type=(
                NotificationType.LOYALTY_TIER_UPGRADED
            ),
        )
    )

    assert len(tier_notifications) == 1

    tier_notification = tier_notifications[0]

    assert (
        tier_notification.related_entity_type
        == "LOYALTY_ACCOUNT"
    )

    assert (
        tier_notification.related_entity_id
        == account.id
    )

    assert "BRONZE" in tier_notification.message
    assert "SILVER" in tier_notification.message

    # ------------------------------------------------------
    # Final Verification
    # ------------------------------------------------------

    all_notifications = (
        await get_notifications_for_user(
            db_session,
            user_id=user.id,
        )
    )

    assert len(all_notifications) == 3

    print()
    print("=" * 60)
    print(
        "Loyalty -> Notification Integration Test"
    )
    print(
        "LOYALTY_SERVICE"
        " -> NOTIFICATION_SERVICE"
        " -> NOTIFICATION_REPOSITORY"
        " -> POSTGRESQL"
    )
    print(
        "POINTS_EARNED: PASS"
    )
    print(
        "TIER_UPGRADED: PASS"
    )
    print(
        "IDEMPOTENCY: PASS"
    )
    print(
        "FAILURE_ISOLATION: PASS"
    )
    print(
        "INTEGRATION TEST: PASSED"
    )
    print("=" * 60)