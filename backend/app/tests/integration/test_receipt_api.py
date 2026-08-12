"""
Receipt API Integration Tests.

These tests exercise the real SmartPark Receipt API through
the FastAPI application.

Architecture under test
-----------------------

    HTTP Request
         |
         v
    FastAPI Receipt Endpoint
         |
         v
    ReceiptService Dependency
         |
         v
    ReceiptRepository
         |
         +--------------------+
         |                    |
         v                    v
    ReceiptPDFService     LocalStorage
         |                    |
         +---------+----------+
                   |
                   v
               PostgreSQL

The test uses:

- Real FastAPI application
- Real PostgreSQL test database
- Real SQLAlchemy AsyncSession
- Real ReceiptRepository
- Real ReceiptService
- Real ReceiptPDFService
- Real LocalStorage
- Real Receipt model
- Real PaymentTransaction model
- Real User model

The test does NOT:

- call Safaricom/M-Pesa
- call Supabase
- use production database
- use mocked ReceiptService
- use mocked ReceiptRepository
- use mocked ReceiptPDFService
- use mocked StorageService

Authentication
--------------

The authenticated-user dependency is overridden with a real
database User object.

This allows the test to focus on the Receipt API and its
downstream service/storage/database pipeline without making
the test depend on the separate login API.

The authentication endpoint itself should be tested separately
by the Auth API integration tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
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

from app.config import settings
from app.database.dependencies import get_db as dependencies_get_db
from app.database.session import get_db as session_get_db
from app.main import app
from app.models.enums import (
    Currency,
    PaymentMethod,
    PaymentProvider,
    PaymentPurpose,
    PaymentStatus,
    PaymentType,
    ReceiptStatus,
    ReceiptType,
    UserRole,
)
from app.models.payment_transaction import PaymentTransaction
from app.models.receipt import Receipt
from app.models.user import User
from app.services.receipt_service import ReceiptService
from app.storage.factory import storage_service
import app.storage.factory as storage_factory

from app.api.dependencies.auth import (
    get_current_active_user,
)


# ==========================================================
# Test Database
# ==========================================================


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """
    Create a real asynchronous PostgreSQL test database session.

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
# Test User
# ==========================================================


async def create_test_user(
    db: AsyncSession,
) -> User:
    """
    Create a real test user in PostgreSQL.

    The user is used as:

    - Receipt.customer_id
    - authenticated API user
    """

    unique_id = uuid4().hex[:10].lower()

    user = User(
        first_name="SmartPark",
        last_name="API Test",
        email=f"receipt.api.{unique_id}@test.local",
        phone_number=f"0712{unique_id[:6]}",
        password_hash="integration-test-password-hash",
        role=UserRole.DRIVER,
        is_active=True,
    )

    db.add(user)

    await db.flush()
    await db.refresh(user)

    return user


# ==========================================================
# Payment Factory
# ==========================================================


def build_payment(
    *,
    customer_id: int,
) -> PaymentTransaction:
    """
    Build a successful PaymentTransaction suitable for
    Receipt creation.
    """

    unique_id = uuid4().hex[:12].upper()

    return PaymentTransaction(
        transaction_number=f"API-IT-{unique_id}",

        # ------------------------------------------------------
        # References
        # ------------------------------------------------------

        reservation_id=None,
        parking_session_id=None,
        customer_id=customer_id,
        parent_transaction_id=None,

        # ------------------------------------------------------
        # Payment identity
        # ------------------------------------------------------

        payment_type=PaymentType.PAYMENT,
        payment_purpose=PaymentPurpose.PARKING_SESSION,
        payment_method=PaymentMethod.MPESA,
        payment_provider=PaymentProvider.SAFARICOM,
        currency=Currency.KES,

        # ------------------------------------------------------
        # Financial snapshot
        # ------------------------------------------------------

        subtotal_amount=Decimal("400.00"),
        discount_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("400.00"),

        # ------------------------------------------------------
        # Provider information
        # ------------------------------------------------------

        external_reference=f"API-EXT-{unique_id}",
        receipt_number=f"QK{unique_id}",
        provider_transaction_id=f"API-MPESA-{unique_id}",
        provider_status_message="Receipt API integration test",
        provider_response={
            "test": True,
            "provider": "SAFARICOM",
            "reference": unique_id,
        },

        # ------------------------------------------------------
        # Payer information
        # ------------------------------------------------------

        payer_name="SmartPark API Test Customer",
        payer_phone="0712345678",
        payer_email="receipt.api@test.local",

        # ------------------------------------------------------
        # Status
        # ------------------------------------------------------

        status=PaymentStatus.SUCCESSFUL,
        paid_at=datetime.now(timezone.utc),

        notes="Receipt API integration test",

        # ------------------------------------------------------
        # Optional fields
        # ------------------------------------------------------

        balance_after=None,
        is_reconciled=False,

        idempotency_key=(
            f"receipt-api-integration-{unique_id}"
        ),

        loyalty_points_earned=0,
        loyalty_points_redeemed=0,
    )


# ==========================================================
# Storage Test Isolation
# ==========================================================


@pytest_asyncio.fixture
async def isolated_local_storage():
    """
    Provide a temporary filesystem location for the real
    LocalStorage implementation.

    This prevents the API integration test from polluting
    the application's normal storage directory.
    """

    temporary_directory = TemporaryDirectory(
        prefix="smartpark_receipt_api_test_",
    )

    original_storage_path = settings.LOCAL_STORAGE_PATH
    original_storage_service = (
        storage_factory._storage_service
    )

    try:
        settings.LOCAL_STORAGE_PATH = (
            temporary_directory.name
        )

        #
        # Force the factory to create a new LocalStorage
        # instance using the temporary directory.
        #
        storage_factory._storage_service = None

        yield Path(
            temporary_directory.name
        )

    finally:

        #
        # Restore application configuration/state.
        #
        settings.LOCAL_STORAGE_PATH = (
            original_storage_path
        )

        storage_factory._storage_service = (
            original_storage_service
        )

        temporary_directory.cleanup()


# ==========================================================
# Dependency Overrides
# ==========================================================


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession,
    isolated_local_storage,
):
    """
    Create an asynchronous HTTP client against the real
    FastAPI application.

    The database dependency is overridden so all API-layer
    operations use the test PostgreSQL session.

    The active-user dependency is overridden with the real
    test User created in PostgreSQL.
    """

    test_user = await create_test_user(
        db_session,
    )

    async def override_get_db():
        yield db_session

    async def override_current_active_user():
        return test_user

    #
    # The application has two get_db imports in the current
    # architecture:
    #
    # - app.database.dependencies.get_db
    # - app.database.session.get_db
    #
    # Override both to ensure every relevant dependency uses
    # the same test AsyncSession.
    #

    app.dependency_overrides[
        dependencies_get_db
    ] = override_get_db

    app.dependency_overrides[
        session_get_db
    ] = override_get_db

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

    #
    # Always remove overrides after the test.
    #

    app.dependency_overrides.clear()


# ==========================================================
# Seed Receipt
# ==========================================================


async def create_test_receipt(
    db: AsyncSession,
    user: User,
) -> Receipt:
    """
    Create a real PaymentTransaction and Receipt in PostgreSQL.

    Receipt creation itself is delegated to the real
    ReceiptService.

    This verifies that the API test starts with the same
    receipt lifecycle used by the application.
    """

    payment = build_payment(
        customer_id=user.id,
    )

    db.add(payment)

    await db.flush()
    await db.refresh(payment)

    #
    # Construct the real ReceiptService.
    #
    # NotificationService is intentionally omitted here
    # because this setup phase only needs to create the
    # receipt record. The API generation request below uses
    # the application's real ReceiptService dependency.
    #

    from app.repositories.receipt_repository import (
        ReceiptRepository,
    )

    from app.services.receipt_pdf_service import (
        ReceiptPDFService,
    )

    receipt_repository = ReceiptRepository(
        db=db,
    )

    pdf_service = ReceiptPDFService()

    storage = storage_service()

    receipt_service = ReceiptService(
        db=db,
        repository=receipt_repository,
        storage_service=storage,
        pdf_service=pdf_service,
        notification_service=None,
    )

    receipt = await receipt_service.create_receipt(
        payment=payment,
    )

    assert receipt.id is not None
    assert receipt.customer_id == user.id
    assert receipt.payment_transaction_id == payment.id
    assert receipt.status == ReceiptStatus.PENDING

    return receipt


# ==========================================================
# Receipt API Integration Test
# ==========================================================


@pytest.mark.asyncio
async def test_receipt_api_complete_integration(
    db_session: AsyncSession,
    api_client,
):
    """
    Exercise the complete Receipt API lifecycle.

    Workflow
    --------

        Real PaymentTransaction
                 |
                 v
        Real ReceiptService
                 |
                 v
        Real Receipt
                 |
                 v
        HTTP GET /receipts/{id}
                 |
                 v
        HTTP POST /receipts/{id}/generate
                 |
                 v
        ReceiptPDFService
                 |
                 v
        LocalStorage
                 |
                 v
        PostgreSQL Receipt Update
                 |
                  +--------------------+
                  |                    |
                  v                    v
              GET /url           GET /download
                  |
                  v
              PDF response

    Additional public endpoints tested:

        /receipts/lookup/{receipt_number}
        /receipts/verify/{receipt_number}
    """

    client, user = api_client

    # ------------------------------------------------------
    # Create real Receipt
    # ------------------------------------------------------

    receipt = await create_test_receipt(
        db=db_session,
        user=user,
    )

    receipt_id = receipt.id
    receipt_number = receipt.receipt_number
    verification_token = receipt.verification_token

    assert receipt_id is not None

    print(
        f"\nReceipt created: "
        f"{receipt_number}"
    )

    # ======================================================
    # 1. GET /receipts
    # ======================================================

    response = await client.get(
        "/receipts",
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert "total" in data
    assert "items" in data

    assert any(
        item["id"] == receipt_id
        for item in data["items"]
    )

    print(
        "GET /receipts: OK"
    )

    # ======================================================
    # 2. GET /receipts/{receipt_id}
    # ======================================================

    response = await client.get(
        f"/receipts/{receipt_id}",
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["id"] == receipt_id
    assert data["receipt_number"] == receipt_number
    assert data["customer_id"] == user.id
    assert data["status"] == ReceiptStatus.PENDING.value
    assert data["total_amount"] == "400.00"

    print(
        "GET /receipts/{id}: OK"
    )

    # ======================================================
    # 3. GET /receipts/number/{receipt_number}
    # ======================================================

    response = await client.get(
        f"/receipts/number/{receipt_number}",
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["id"] == receipt_id
    assert data["receipt_number"] == receipt_number

    print(
        "GET /receipts/number/{receipt_number}: OK"
    )

    # ======================================================
    # 4. Public Receipt Lookup
    # ======================================================

    response = await client.get(
        f"/receipts/lookup/{receipt_number}",
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["receipt_number"] == receipt_number
    assert data["payment_transaction_id"] == (
        receipt.payment_transaction_id
    )
    assert data["total_amount"] == "400.00"
    assert data["currency"] == "KES"

    #
    # Verification token must NOT be exposed.
    #
    assert "verification_token" not in data

    print(
        "GET /receipts/lookup/{receipt_number}: OK"
    )

    # ======================================================
    # 5. Verify PENDING Receipt
    # ======================================================

    #
    # A receipt must not be considered customer-facing
    # valid until its PDF has been successfully generated
    # and the receipt reaches AVAILABLE status.
    #

    response = await client.get(
        f"/receipts/verify/{receipt_number}",
        params={
            "verification_token": verification_token,
        },
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["valid"] is False
    assert data["receipt_number"] == receipt_number
    assert data["status"] == ReceiptStatus.PENDING.value
    assert data["payment_transaction_id"] == (
        receipt.payment_transaction_id
    )

    #
    # Token must never be returned.
    #
    assert "verification_token" not in data

    print(
        "PENDING receipt correctly rejected by verification: OK"
    )

    # ======================================================
    # 6. Generate Receipt PDF
    # ======================================================

    response = await client.post(
        f"/receipts/{receipt_id}/generate",
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["id"] == receipt_id
    assert data["receipt_number"] == receipt_number

    assert data["status"] == (
        ReceiptStatus.AVAILABLE.value
    )

    assert data["pdf_storage_path"] is not None
    assert data["pdf_url"] is not None
    assert data["generated_at"] is not None
    assert data["available_at"] is not None
    assert data["failure_reason"] is None

    storage_path = data[
        "pdf_storage_path"
    ]

    pdf_url = data[
        "pdf_url"
    ]

    print(
        "POST /receipts/{id}/generate: OK"
    )

    # ======================================================
    # 7. Verify PostgreSQL Receipt Update
    # ======================================================

    result = await db_session.execute(
        select(Receipt).where(
            Receipt.id == receipt_id,
        )
    )

    persisted_receipt = (
        result.scalar_one()
    )

    assert persisted_receipt.status == (
        ReceiptStatus.AVAILABLE
    )

    assert persisted_receipt.pdf_storage_path == (
        storage_path
    )

    assert persisted_receipt.pdf_url == (
        pdf_url
    )

    assert persisted_receipt.generated_at is not None

    assert persisted_receipt.available_at is not None

    print(
        "PostgreSQL Receipt update: OK"
    )

    # ======================================================
    # 8. Verify Physical LocalStorage File
    # ======================================================

    storage = storage_service()

    assert await storage.exists(
        path=storage_path,
    )

    pdf_bytes = await storage.download(
        path=storage_path,
    )

    assert isinstance(
        pdf_bytes,
        bytes,
    )

    assert len(pdf_bytes) > 0

    assert pdf_bytes.startswith(
        b"%PDF",
    )

    print(
        "LocalStorage PDF file: OK"
    )

    # ======================================================
    # 9. Verify AVAILABLE Receipt
    # ======================================================

    #
    # The receipt is now AVAILABLE, so the same valid
    # verification token must successfully verify it.
    #

    response = await client.get(
        f"/receipts/verify/{receipt_number}",
        params={
            "verification_token": verification_token,
        },
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["valid"] is True
    assert data["receipt_number"] == receipt_number
    assert data["status"] == ReceiptStatus.AVAILABLE.value
    assert data["payment_transaction_id"] == (
        receipt.payment_transaction_id
    )

    #
    # Token must never be returned.
    #
    assert "verification_token" not in data

    print(
        "AVAILABLE receipt verification: OK"
    )

    # ======================================================
    # 10. GET Receipt URL
    # ======================================================

    response = await client.get(
        f"/receipts/{receipt_id}/url",
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["receipt_number"] == receipt_number
    assert data["url"]

    print(
        "GET /receipts/{id}/url: OK"
    )

    # ======================================================
    # 11. Download Receipt PDF
    # ======================================================

    response = await client.get(
        f"/receipts/{receipt_id}/download",
    )

    assert response.status_code == 200, response.text

    assert response.headers[
        "content-type"
    ].startswith(
        "application/pdf"
    )

    assert (
        response.headers[
            "content-disposition"
        ].startswith(
            "attachment;"
        )
    )

    assert response.content.startswith(
        b"%PDF",
    )

    assert len(response.content) > 0

    print(
        "GET /receipts/{id}/download: OK"
    )

    # ======================================================
    # 12. Verify Downloaded PDF Equals Stored PDF
    # ======================================================

    assert response.content == pdf_bytes

    print(
        "API PDF download matches LocalStorage: OK"
    )

    # ======================================================
    # 13. Idempotent Generate
    # ======================================================

    response = await client.post(
        f"/receipts/{receipt_id}/generate",
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["status"] == (
        ReceiptStatus.AVAILABLE.value
    )

    assert data["receipt_number"] == receipt_number
    assert data["pdf_storage_path"] == storage_path

    print(
        "Receipt generation idempotency: OK"
    )

    # ======================================================
    # 14. Invalid Verification Token
    # ======================================================

    response = await client.get(
        f"/receipts/verify/{receipt_number}",
        params={
            "verification_token": "INVALID-TOKEN",
        },
    )

    #
    # The verification service currently returns HTTP 200
    # with valid=False for a token mismatch.
    #
    assert response.status_code == 200, response.text

    data = response.json()

    assert data["valid"] is False
    assert data["receipt_number"] == receipt_number
    assert data["status"] == ReceiptStatus.AVAILABLE.value

    assert "verification_token" not in data

    print(
        "Invalid verification token rejected: OK"
    )

    # ======================================================
    # 15. Non-existent Receipt
    # ======================================================

    response = await client.get(
        "/receipts/999999999",
    )

    assert response.status_code == 404

    print(
        "Non-existent receipt rejected: OK"
    )

    # ======================================================
    # 16. Unauthenticated Access
    # ======================================================

    #
    # Temporarily remove the active-user override.
    #
    # Public lookup/verification remain available, while
    # authenticated receipt endpoints should reject access.
    #

    original_override = app.dependency_overrides.get(
        get_current_active_user
    )

    app.dependency_overrides.pop(
        get_current_active_user,
        None,
    )

    try:

        response = await client.get(
            "/receipts",
        )

        assert response.status_code == 401

        print(
            "Unauthenticated /receipts access rejected: OK"
        )

    finally:

        if original_override is not None:
            app.dependency_overrides[
                get_current_active_user
            ] = original_override

    # ======================================================
    # Final
    # ======================================================

    print(
        "\n"
        "====================================================\n"
        "Receipt API Integration Test\n"
        "FASTAPI -> RECEIPTS -> SERVICE -> PDF -> STORAGE -> POSTGRES\n"
        "INTEGRATION TEST: PASSED\n"
        "===================================================="
    )