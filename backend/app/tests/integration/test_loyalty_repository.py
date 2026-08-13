"""
Loyalty Repository Integration Tests.

These tests exercise the real LoyaltyRepository against the
real PostgreSQL test database.

Architecture under test
-----------------------

    Test
      |
      v
LoyaltyRepository
      |
      v
SQLAlchemy AsyncSession
      |
      v
PostgreSQL Test Database

The tests use:

- Real PostgreSQL test database
- Real SQLAlchemy AsyncSession
- Real User model
- Real LoyaltyAccount model
- Real LoyaltyPointTransaction model
- Real LoyaltyRepository

The tests do NOT:

- use the LoyaltyService
- use FastAPI
- use mocked repositories
- use the production/development database
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

from app.models.enums import (
    LoyaltyPointTransactionType,
    LoyaltyTier,
    UserRole,
)

from app.models.loyalty_account import (
    LoyaltyAccount,
)

from app.models.loyalty_point_transaction import (
    LoyaltyPointTransaction,
)

from app.models.user import User

from app.repositories.loyalty_repository import (
    LoyaltyRepository,
)


# ==========================================================
# Test Database
# ==========================================================


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """
    Create a real asynchronous PostgreSQL test database
    session.

    The test database is taken from:

        settings.TEST_DATABASE_URL

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
) -> User:
    """
    Create a real test user in PostgreSQL.

    The user is used as the customer associated with the
    LoyaltyAccount.
    """

    unique_id = uuid4().hex[:10].lower()

    user = User(
        first_name="SmartPark",
        last_name="Loyalty Test",
        email=f"loyalty.repo.{unique_id}@test.local",
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
    customer_id: int,
    *,
    points_balance: int = 0,
    lifetime_points: int = 0,
    tier: LoyaltyTier = LoyaltyTier.BRONZE,
    is_active: bool = True,
) -> LoyaltyAccount:
    """
    Create a real LoyaltyAccount in PostgreSQL.
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
# Loyalty Point Transaction Factory
# ==========================================================


async def create_test_point_transaction(
    db: AsyncSession,
    loyalty_account_id: int,
    *,
    transaction_type: LoyaltyPointTransactionType,
    points: int,
    balance_after: int,
    reference_type: str | None = None,
    reference_id: int | None = None,
    description: str | None = None,
) -> LoyaltyPointTransaction:
    """
    Create a real LoyaltyPointTransaction in PostgreSQL.
    """

    transaction = LoyaltyPointTransaction(
        loyalty_account_id=loyalty_account_id,
        transaction_type=transaction_type,
        points=points,
        balance_after=balance_after,
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
    )

    db.add(transaction)

    await db.flush()
    await db.refresh(transaction)

    return transaction


# ==========================================================
# Repository Fixture
# ==========================================================


@pytest_asyncio.fixture
async def loyalty_repository(
    db_session: AsyncSession,
) -> LoyaltyRepository:
    """
    Return a real LoyaltyRepository using the real
    PostgreSQL test session.
    """

    return LoyaltyRepository(
        db=db_session,
    )


# ==========================================================
# Tests
# ==========================================================


@pytest.mark.asyncio
async def test_create_and_get_loyalty_account(
    db_session: AsyncSession,
    loyalty_repository: LoyaltyRepository,
):
    """
    Verify that a loyalty account can be persisted and
    retrieved by ID.
    """

    user = await create_test_user(
        db_session,
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        points_balance=250,
        lifetime_points=500,
        tier=LoyaltyTier.BRONZE,
    )

    retrieved = await loyalty_repository.get_by_id(
        account.id,
    )

    assert retrieved is not None
    assert retrieved.id == account.id
    assert retrieved.customer_id == user.id
    assert retrieved.points_balance == 250
    assert retrieved.lifetime_points == 500
    assert retrieved.tier == LoyaltyTier.BRONZE
    assert retrieved.is_active is True

    print(
        "Create/Get LoyaltyAccount: OK"
    )


@pytest.mark.asyncio
async def test_get_loyalty_account_by_customer_id(
    db_session: AsyncSession,
    loyalty_repository: LoyaltyRepository,
):
    """
    Verify customer-based loyalty account lookup.
    """

    user = await create_test_user(
        db_session,
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    retrieved = await loyalty_repository.get_by_customer_id(
        user.id,
    )

    assert retrieved is not None
    assert retrieved.id == account.id
    assert retrieved.customer_id == user.id

    print(
        "Get LoyaltyAccount by customer ID: OK"
    )


@pytest.mark.asyncio
async def test_loyalty_account_not_found(
    loyalty_repository: LoyaltyRepository,
):
    """
    Verify that missing loyalty accounts return None.
    """

    account = await loyalty_repository.get_by_customer_id(
        999999999,
    )

    assert account is None

    print(
        "Missing LoyaltyAccount correctly returns None: OK"
    )


@pytest.mark.asyncio
async def test_loyalty_account_exists_for_customer(
    db_session: AsyncSession,
    loyalty_repository: LoyaltyRepository,
):
    """
    Verify exists_for_customer().
    """

    user = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    exists = await loyalty_repository.exists_for_customer(
        user.id,
    )

    missing = await loyalty_repository.exists_for_customer(
        999999999,
    )

    assert exists is True
    assert missing is False

    print(
        "LoyaltyAccount existence check: OK"
    )


@pytest.mark.asyncio
async def test_get_active_loyalty_account(
    db_session: AsyncSession,
    loyalty_repository: LoyaltyRepository,
):
    """
    Verify active customer loyalty account lookup.
    """

    user = await create_test_user(
        db_session,
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        is_active=True,
    )

    retrieved = (
        await loyalty_repository.get_active_by_customer_id(
            user.id,
        )
    )

    assert retrieved is not None
    assert retrieved.id == account.id
    assert retrieved.is_active is True

    print(
        "Get active LoyaltyAccount: OK"
    )


@pytest.mark.asyncio
async def test_inactive_loyalty_account_not_returned_as_active(
    db_session: AsyncSession,
    loyalty_repository: LoyaltyRepository,
):
    """
    Verify inactive loyalty accounts are excluded from
    active-account lookup.
    """

    user = await create_test_user(
        db_session,
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        is_active=False,
    )

    retrieved = (
        await loyalty_repository.get_active_by_customer_id(
            user.id,
        )
    )

    assert retrieved is None

    # The account itself still exists.
    existing = await loyalty_repository.get_by_id(
        account.id,
    )

    assert existing is not None
    assert existing.is_active is False

    print(
        "Inactive LoyaltyAccount correctly excluded: OK"
    )


@pytest.mark.asyncio
async def test_get_all_active_loyalty_accounts(
    db_session: AsyncSession,
    loyalty_repository: LoyaltyRepository,
):
    """
    Verify retrieval of active loyalty accounts with
    pagination.
    """

    user_one = await create_test_user(
        db_session,
    )

    user_two = await create_test_user(
        db_session,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user_one.id,
        is_active=True,
    )

    await create_test_loyalty_account(
        db_session,
        customer_id=user_two.id,
        is_active=False,
    )

    accounts = await loyalty_repository.get_all_active(
        limit=100,
        offset=0,
    )

    account_customer_ids = {
        account.customer_id
        for account in accounts
    }

    assert user_one.id in account_customer_ids
    assert user_two.id not in account_customer_ids

    print(
        "Get active LoyaltyAccounts with pagination: OK"
    )


@pytest.mark.asyncio
async def test_create_and_get_point_transaction(
    db_session: AsyncSession,
    loyalty_repository: LoyaltyRepository,
):
    """
    Verify creation and retrieval of a loyalty point
    transaction.
    """

    user = await create_test_user(
        db_session,
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        points_balance=100,
        lifetime_points=100,
    )

    transaction = await create_test_point_transaction(
        db_session,
        loyalty_account_id=account.id,
        transaction_type=(
            LoyaltyPointTransactionType.EARN
        ),
        points=100,
        balance_after=100,
        reference_type="PAYMENT_TRANSACTION",
        reference_id=12345,
        description="Parking payment loyalty points",
    )

    retrieved = (
        await loyalty_repository.get_point_transaction_by_id(
            transaction.id,
        )
    )

    assert retrieved is not None
    assert retrieved.id == transaction.id
    assert retrieved.loyalty_account_id == account.id
    assert retrieved.transaction_type == (
        LoyaltyPointTransactionType.EARN
    )
    assert retrieved.points == 100
    assert retrieved.balance_after == 100
    assert retrieved.reference_type == (
        "PAYMENT_TRANSACTION"
    )
    assert retrieved.reference_id == 12345
    assert retrieved.description == (
        "Parking payment loyalty points"
    )

    print(
        "Create/Get LoyaltyPointTransaction: OK"
    )


@pytest.mark.asyncio
async def test_get_point_transactions(
    db_session: AsyncSession,
    loyalty_repository: LoyaltyRepository,
):
    """
    Verify point transaction history retrieval.
    """

    user = await create_test_user(
        db_session,
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        points_balance=150,
        lifetime_points=150,
    )

    first = await create_test_point_transaction(
        db_session,
        loyalty_account_id=account.id,
        transaction_type=(
            LoyaltyPointTransactionType.EARN
        ),
        points=100,
        balance_after=100,
        description="First earning transaction",
    )

    second = await create_test_point_transaction(
        db_session,
        loyalty_account_id=account.id,
        transaction_type=(
            LoyaltyPointTransactionType.EARN
        ),
        points=50,
        balance_after=150,
        description="Second earning transaction",
    )

    transactions = (
        await loyalty_repository.get_point_transactions(
            loyalty_account_id=account.id,
            limit=100,
            offset=0,
        )
    )

    transaction_ids = {
        transaction.id
        for transaction in transactions
    }

    assert first.id in transaction_ids
    assert second.id in transaction_ids
    assert len(transactions) == 2

    print(
        "Get point transaction history: OK"
    )


@pytest.mark.asyncio
async def test_get_point_transactions_by_type(
    db_session: AsyncSession,
    loyalty_repository: LoyaltyRepository,
):
    """
    Verify filtering point transactions by transaction type.
    """

    user = await create_test_user(
        db_session,
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    earn_transaction = (
        await create_test_point_transaction(
            db_session,
            loyalty_account_id=account.id,
            transaction_type=(
                LoyaltyPointTransactionType.EARN
            ),
            points=100,
            balance_after=100,
        )
    )

    await create_test_point_transaction(
        db_session,
        loyalty_account_id=account.id,
        transaction_type=(
            LoyaltyPointTransactionType.REDEEM
        ),
        points=-50,
        balance_after=50,
    )

    transactions = (
        await loyalty_repository.get_point_transactions_by_type(
            loyalty_account_id=account.id,
            transaction_type=(
                LoyaltyPointTransactionType.EARN
            ),
        )
    )

    assert len(transactions) == 1
    assert transactions[0].id == earn_transaction.id
    assert transactions[0].transaction_type == (
        LoyaltyPointTransactionType.EARN
    )

    print(
        "Filter point transactions by type: OK"
    )


@pytest.mark.asyncio
async def test_get_latest_point_transaction(
    db_session: AsyncSession,
    loyalty_repository: LoyaltyRepository,
):
    """
    Verify retrieval of the latest point transaction.
    """

    user = await create_test_user(
        db_session,
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    first = await create_test_point_transaction(
        db_session,
        loyalty_account_id=account.id,
        transaction_type=(
            LoyaltyPointTransactionType.EARN
        ),
        points=100,
        balance_after=100,
        description="First transaction",
    )

    second = await create_test_point_transaction(
        db_session,
        loyalty_account_id=account.id,
        transaction_type=(
            LoyaltyPointTransactionType.EARN
        ),
        points=50,
        balance_after=150,
        description="Latest transaction",
    )

    latest = (
        await loyalty_repository.get_latest_point_transaction(
            loyalty_account_id=account.id,
        )
    )

    assert latest is not None
    assert latest.id == second.id
    assert latest.id != first.id
    assert latest.description == "Latest transaction"

    print(
        "Get latest point transaction: OK"
    )


@pytest.mark.asyncio
async def test_get_point_transactions_by_reference(
    db_session: AsyncSession,
    loyalty_repository: LoyaltyRepository,
):
    """
    Verify lookup of loyalty transactions using a business
    reference.
    """

    user = await create_test_user(
        db_session,
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    matching_transaction = (
        await create_test_point_transaction(
            db_session,
            loyalty_account_id=account.id,
            transaction_type=(
                LoyaltyPointTransactionType.EARN
            ),
            points=100,
            balance_after=100,
            reference_type="PAYMENT_TRANSACTION",
            reference_id=5001,
        )
    )

    await create_test_point_transaction(
        db_session,
        loyalty_account_id=account.id,
        transaction_type=(
            LoyaltyPointTransactionType.EARN
        ),
        points=50,
        balance_after=150,
        reference_type="PAYMENT_TRANSACTION",
        reference_id=5002,
    )

    transactions = (
        await loyalty_repository.get_by_reference(
            reference_type="PAYMENT_TRANSACTION",
            reference_id=5001,
        )
    )

    assert len(transactions) == 1
    assert transactions[0].id == matching_transaction.id
    assert transactions[0].reference_type == (
        "PAYMENT_TRANSACTION"
    )
    assert transactions[0].reference_id == 5001

    print(
        "Get point transactions by reference: OK"
    )


@pytest.mark.asyncio
async def test_count_point_transactions(
    db_session: AsyncSession,
    loyalty_repository: LoyaltyRepository,
):
    """
    Verify point transaction count.
    """

    user = await create_test_user(
        db_session,
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    await create_test_point_transaction(
        db_session,
        loyalty_account_id=account.id,
        transaction_type=(
            LoyaltyPointTransactionType.EARN
        ),
        points=100,
        balance_after=100,
    )

    await create_test_point_transaction(
        db_session,
        loyalty_account_id=account.id,
        transaction_type=(
            LoyaltyPointTransactionType.REDEEM
        ),
        points=-50,
        balance_after=50,
    )

    await create_test_point_transaction(
        db_session,
        loyalty_account_id=account.id,
        transaction_type=(
            LoyaltyPointTransactionType.ADJUSTMENT
        ),
        points=25,
        balance_after=75,
    )

    count = (
        await loyalty_repository.count_point_transactions(
            loyalty_account_id=account.id,
        )
    )

    assert count == 3

    print(
        "Count point transactions: OK"
    )


@pytest.mark.asyncio
async def test_point_transaction_pagination(
    db_session: AsyncSession,
    loyalty_repository: LoyaltyRepository,
):
    """
    Verify limit and offset behavior for point transaction
    history.
    """

    user = await create_test_user(
        db_session,
    )

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
    )

    for index in range(5):
        await create_test_point_transaction(
            db_session,
            loyalty_account_id=account.id,
            transaction_type=(
                LoyaltyPointTransactionType.EARN
            ),
            points=10,
            balance_after=(index + 1) * 10,
            description=f"Transaction {index + 1}",
        )

    first_page = (
        await loyalty_repository.get_point_transactions(
            loyalty_account_id=account.id,
            limit=2,
            offset=0,
        )
    )

    second_page = (
        await loyalty_repository.get_point_transactions(
            loyalty_account_id=account.id,
            limit=2,
            offset=2,
        )
    )

    assert len(first_page) == 2
    assert len(second_page) == 2

    first_page_ids = {
        transaction.id
        for transaction in first_page
    }

    second_page_ids = {
        transaction.id
        for transaction in second_page
    }

    assert first_page_ids.isdisjoint(
        second_page_ids,
    )

    print(
        "Point transaction pagination: OK"
    )


# ==========================================================
# Complete Repository Integration Test
# ==========================================================


@pytest.mark.asyncio
async def test_loyalty_repository_complete_integration(
    db_session: AsyncSession,
    loyalty_repository: LoyaltyRepository,
):
    """
    Exercise the complete LoyaltyRepository persistence and
    retrieval lifecycle.

    Workflow
    --------

        User
         |
         v
        LoyaltyAccount
         |
         +-------------------------+
         |                         |
         v                         v
    Account Lookup          Point Transactions
                                   |
                     +-------------+-------------+
                     |             |             |
                     v             v             v
                   EARN         REDEEM       REFERRAL
                                   |
                                   v
                              Reference Lookup
                                   |
                                   v
                                Count
    """

    # ======================================================
    # 1. Create customer
    # ======================================================

    user = await create_test_user(
        db_session,
    )

    assert user.id is not None

    print(
        f"Test customer created: {user.id}"
    )

    # ======================================================
    # 2. Create loyalty account
    # ======================================================

    account = await create_test_loyalty_account(
        db_session,
        customer_id=user.id,
        points_balance=500,
        lifetime_points=1_500,
        tier=LoyaltyTier.SILVER,
    )

    assert account.id is not None
    assert account.customer_id == user.id
    assert account.points_balance == 500
    assert account.lifetime_points == 1_500
    assert account.tier == LoyaltyTier.SILVER

    print(
        "LoyaltyAccount creation: OK"
    )

    # ======================================================
    # 3. Retrieve by customer
    # ======================================================

    retrieved_account = (
        await loyalty_repository.get_by_customer_id(
            user.id,
        )
    )

    assert retrieved_account is not None
    assert retrieved_account.id == account.id

    print(
        "LoyaltyAccount customer lookup: OK"
    )

    # ======================================================
    # 4. Create earning transaction
    # ======================================================

    earn_transaction = (
        await create_test_point_transaction(
            db_session,
            loyalty_account_id=account.id,
            transaction_type=(
                LoyaltyPointTransactionType.EARN
            ),
            points=100,
            balance_after=600,
            reference_type="PAYMENT_TRANSACTION",
            reference_id=9001,
            description="Parking payment points",
        )
    )

    print(
        "EARN transaction creation: OK"
    )

    # ======================================================
    # 5. Create redemption transaction
    # ======================================================

    redeem_transaction = (
        await create_test_point_transaction(
            db_session,
            loyalty_account_id=account.id,
            transaction_type=(
                LoyaltyPointTransactionType.REDEEM
            ),
            points=-200,
            balance_after=400,
            reference_type="REWARD_REDEMPTION",
            reference_id=3001,
            description="Free parking reward redemption",
        )
    )

    print(
        "REDEEM transaction creation: OK"
    )

    # ======================================================
    # 6. Create referral transaction
    # ======================================================

    referral_transaction = (
        await create_test_point_transaction(
            db_session,
            loyalty_account_id=account.id,
            transaction_type=(
                LoyaltyPointTransactionType.REFERRAL_BONUS
            ),
            points=500,
            balance_after=900,
            reference_type="REFERRAL",
            reference_id=7001,
            description="Referral bonus",
        )
    )

    print(
        "REFERRAL transaction creation: OK"
    )

    # ======================================================
    # 7. Retrieve complete history
    # ======================================================

    history = (
        await loyalty_repository.get_point_transactions(
            loyalty_account_id=account.id,
            limit=100,
            offset=0,
        )
    )

    history_ids = {
        transaction.id
        for transaction in history
    }

    assert earn_transaction.id in history_ids
    assert redeem_transaction.id in history_ids
    assert referral_transaction.id in history_ids
    assert len(history) == 3

    print(
        "Complete point history retrieval: OK"
    )

    # ======================================================
    # 8. Filter by transaction type
    # ======================================================

    referral_transactions = (
        await loyalty_repository.get_point_transactions_by_type(
            loyalty_account_id=account.id,
            transaction_type=(
                LoyaltyPointTransactionType.REFERRAL_BONUS
            ),
        )
    )

    assert len(referral_transactions) == 1
    assert referral_transactions[0].id == (
        referral_transaction.id
    )

    print(
        "Transaction type filtering: OK"
    )

    # ======================================================
    # 9. Reference lookup
    # ======================================================

    payment_transactions = (
        await loyalty_repository.get_by_reference(
            reference_type="PAYMENT_TRANSACTION",
            reference_id=9001,
        )
    )

    assert len(payment_transactions) == 1
    assert payment_transactions[0].id == (
        earn_transaction.id
    )

    print(
        "Reference lookup: OK"
    )

    # ======================================================
    # 10. Latest transaction
    # ======================================================

    latest = (
        await loyalty_repository.get_latest_point_transaction(
            loyalty_account_id=account.id,
        )
    )

    assert latest is not None
    assert latest.id == referral_transaction.id

    print(
        "Latest transaction lookup: OK"
    )

    # ======================================================
    # 11. Transaction count
    # ======================================================

    count = (
        await loyalty_repository.count_point_transactions(
            loyalty_account_id=account.id,
        )
    )

    assert count == 3

    print(
        "Transaction count: OK"
    )

    # ======================================================
    # Final Result
    # ======================================================

    print(
        "\n"
        "====================================================\n"
        "Loyalty Repository Integration Test\n"
        "POSTGRESQL -> LOYALTY ACCOUNT -> POINT LEDGER\n"
        "INTEGRATION TEST: PASSED\n"
        "===================================================="
    )