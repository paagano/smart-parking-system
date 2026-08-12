"""
ReceiptService -> ReceiptPDFService -> LocalStorage integration test.

This test verifies the complete receipt document generation pipeline:

    ReceiptService
        |
        +--> ReceiptPDFService
        |        |
        |        +--> PDF bytes
        |
        +--> LocalStorage
                 |
                 +--> Stored PDF file

This test intentionally does NOT:

- connect to PostgreSQL
- connect to Supabase
- send notifications
- require network access

The test uses:

- Real ReceiptService
- Real ReceiptPDFService
- Real LocalStorage
- An in-memory fake ReceiptRepository
- A temporary filesystem directory provided by pytest

The purpose is to verify that the real PDF generation and real
storage implementations work correctly together through the
ReceiptService orchestration layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.receipt_pdf_service import ReceiptPDFService
from app.services.receipt_service import ReceiptService
from app.storage.local import LocalStorage


# ==========================================================
# Test Receipt Factory
# ==========================================================


def make_receipt(
    **overrides,
):
    """
    Create a receipt-like object containing the fields required
    by ReceiptService and ReceiptPDFService.

    SimpleNamespace is intentionally used because this test is
    focused on service orchestration and storage integration,
    not SQLAlchemy persistence.
    """

    receipt = SimpleNamespace(
        id=1,

        receipt_number="SP-2026-000001",

        receipt_type="PAYMENT",

        status="PENDING",

        payment_transaction_id=1001,

        customer_id=6,

        customer_name="Philip Agano",

        customer_phone="0712345678",

        customer_email="philip@example.com",

        subtotal_amount=Decimal("400.00"),

        discount_amount=Decimal("0.00"),

        tax_amount=Decimal("0.00"),

        total_amount=Decimal("400.00"),

        currency="KES",

        payment_method="M_PESA",

        payment_provider="M-Pesa",

        provider_receipt_number="QK12345678",

        paid_at=datetime(
            2026,
            8,
            12,
            10,
            30,
            0,
            tzinfo=timezone.utc,
        ),

        verification_token="ABCDEF1234567890",

        pdf_storage_path=None,

        pdf_url=None,

        generated_at=None,

        available_at=None,

        failure_reason=None,

        created_at=datetime(
            2026,
            8,
            12,
            10,
            30,
            0,
            tzinfo=timezone.utc,
        ),

        updated_at=datetime(
            2026,
            8,
            12,
            10,
            30,
            0,
            tzinfo=timezone.utc,
        ),
    )

    for key, value in overrides.items():
        setattr(
            receipt,
            key,
            value,
        )

    return receipt


# ==========================================================
# Fake Receipt Repository
# ==========================================================


class FakeReceiptRepository:
    """
    Minimal in-memory ReceiptRepository replacement.

    This intentionally implements only the repository methods
    required by ReceiptService.generate_receipt().
    """

    def __init__(
        self,
        receipt,
    ):
        self.receipt = receipt

        self.save_called = False

        self.commit_called = False

        self.refresh_called = False

    async def get_by_id(
        self,
        receipt_id: int,
    ):
        """
        Return the test receipt when the requested ID matches.
        """

        if receipt_id == self.receipt.id:
            return self.receipt

        return None

    async def save(
        self,
        receipt,
    ):
        """
        Simulate repository persistence.
        """

        self.save_called = True

        self.receipt = receipt

        return receipt

    async def commit(
        self,
    ):
        """
        Simulate database commit.
        """

        self.commit_called = True

    async def refresh(
        self,
        receipt,
    ):
        """
        Simulate SQLAlchemy refresh.

        No database exists in this test, so the object is already
        up to date.
        """

        self.refresh_called = True


# ==========================================================
# Service Factory
# ==========================================================


def build_receipt_service(
    *,
    receipt,
    storage,
):
    """
    Construct a ReceiptService using:

    - Fake repository
    - Real ReceiptPDFService
    - Real LocalStorage
    - Mock database session
    - No notification service

    Returns:
        Tuple containing the service and fake repository.
    """

    repository = FakeReceiptRepository(
        receipt,
    )

    pdf_service = ReceiptPDFService()

    db = Mock(
        name="AsyncSession",
    )

    service = ReceiptService(
        db=db,
        repository=repository,
        storage_service=storage,
        pdf_service=pdf_service,
        notification_service=None,
    )

    return service, repository


# ==========================================================
# Integration Test
# ==========================================================


@pytest.mark.asyncio
async def test_receipt_service_generates_pdf_and_stores_it(
    tmp_path,
):
    """
    Verify the complete:

        ReceiptService
            ->
        ReceiptPDFService
            ->
        LocalStorage

    integration.

    The test proves that:

    1. ReceiptService retrieves the receipt.
    2. ReceiptPDFService generates real PDF bytes.
    3. LocalStorage stores the PDF.
    4. The stored file exists.
    5. The stored file is a valid PDF.
    6. Receipt storage metadata is populated.
    7. Receipt status becomes AVAILABLE.
    8. Generation timestamps are populated.
    9. Repository save/commit/refresh are invoked.
    10. The stored PDF can be downloaded again.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    receipt = make_receipt()

    storage = LocalStorage(
        base_path=tmp_path,
    )

    service, repository = build_receipt_service(
        receipt=receipt,
        storage=storage,
    )

    # Confirm our initial state.
    assert receipt.status == "PENDING"

    assert receipt.pdf_storage_path is None

    assert receipt.pdf_url is None

    assert receipt.generated_at is None

    assert receipt.available_at is None

    assert receipt.failure_reason is None

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    result = await service.generate_receipt(
        receipt_id=receipt.id,
    )

    # ------------------------------------------------------
    # Assert: Service Result
    # ------------------------------------------------------

    assert result is receipt

    # ------------------------------------------------------
    # Assert: Receipt Lifecycle
    # ------------------------------------------------------

    assert receipt.status == "AVAILABLE"

    assert receipt.failure_reason is None

    assert receipt.generated_at is not None

    assert receipt.available_at is not None

    assert isinstance(
        receipt.generated_at,
        datetime,
    )

    assert isinstance(
        receipt.available_at,
        datetime,
    )

    assert receipt.generated_at.tzinfo is not None

    assert receipt.available_at.tzinfo is not None

    # ------------------------------------------------------
    # Assert: Storage Metadata
    # ------------------------------------------------------

    assert receipt.pdf_storage_path is not None

    assert receipt.pdf_storage_path.endswith(
        ".pdf",
    )

    assert receipt.pdf_url is not None

    assert receipt.pdf_url.startswith(
        "/storage/",
    )

    # ------------------------------------------------------
    # Assert: Repository Operations
    # ------------------------------------------------------

    assert repository.save_called is True

    assert repository.commit_called is True

    assert repository.refresh_called is True

    # ------------------------------------------------------
    # Assert: Physical PDF File Exists
    # ------------------------------------------------------

    stored_pdf_path = (
        tmp_path
        / receipt.pdf_storage_path
    )

    assert stored_pdf_path.exists()

    assert stored_pdf_path.is_file()

    # ------------------------------------------------------
    # Assert: PDF File Is Non-Empty
    # ------------------------------------------------------

    pdf_bytes = stored_pdf_path.read_bytes()

    assert isinstance(
        pdf_bytes,
        bytes,
    )

    assert len(pdf_bytes) > 0

    # ------------------------------------------------------
    # Assert: PDF Signature
    # ------------------------------------------------------

    assert pdf_bytes.startswith(
        b"%PDF",
    )

    # ------------------------------------------------------
    # Assert: Download Through Storage Abstraction
    # ------------------------------------------------------

    downloaded_bytes = await storage.download(
        path=receipt.pdf_storage_path,
    )

    assert downloaded_bytes == pdf_bytes

    assert downloaded_bytes.startswith(
        b"%PDF",
    )

    # ------------------------------------------------------
    # Assert: Storage Existence
    # ------------------------------------------------------

    assert await storage.exists(
        path=receipt.pdf_storage_path,
    )

    # ------------------------------------------------------
    # Assert: Storage URL
    # ------------------------------------------------------

    url = await storage.get_url(
        path=receipt.pdf_storage_path,
    )

    assert url == receipt.pdf_url

    print(
        "\nReceiptService -> ReceiptPDFService -> "
        "LocalStorage integration: OK"
    )

    print(
        f"Receipt number: {receipt.receipt_number}"
    )

    print(
        f"Receipt status: {receipt.status}"
    )

    print(
        f"Storage path: {receipt.pdf_storage_path}"
    )

    print(
        f"PDF size: {len(pdf_bytes)} bytes"
    )


# ==========================================================
# Storage Cleanup Verification
# ==========================================================


@pytest.mark.asyncio
async def test_receipt_pdf_can_be_deleted_after_generation(
    tmp_path,
):
    """
    Verify that the PDF generated by ReceiptService can be
    removed through the same StorageService abstraction.

    This confirms that the stored document lifecycle is not
    limited to upload/download.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    receipt = make_receipt(
        receipt_number="SP-2026-000002",
        verification_token="ZYXWVUT987654321",
    )

    storage = LocalStorage(
        base_path=tmp_path,
    )

    service, _ = build_receipt_service(
        receipt=receipt,
        storage=storage,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    await service.generate_receipt(
        receipt_id=receipt.id,
    )

    # ------------------------------------------------------
    # Assert Before Delete
    # ------------------------------------------------------

    assert receipt.pdf_storage_path is not None

    assert await storage.exists(
        path=receipt.pdf_storage_path,
    )

    # ------------------------------------------------------
    # Delete
    # ------------------------------------------------------

    await storage.delete(
        path=receipt.pdf_storage_path,
    )

    # ------------------------------------------------------
    # Assert After Delete
    # ------------------------------------------------------

    assert not await storage.exists(
        path=receipt.pdf_storage_path,
    )

    print(
        "\nReceipt PDF storage deletion: OK"
    )


# ==========================================================
# Failure Handling
# ==========================================================


@pytest.mark.asyncio
async def test_receipt_service_marks_receipt_failed_when_storage_fails(
    tmp_path,
):
    """
    Verify ReceiptService failure handling when storage upload
    fails.

    The real ReceiptPDFService is still used.

    Only the storage upload operation is deliberately replaced
    with a failing implementation.

    This verifies that a storage failure does not incorrectly
    leave the receipt marked AVAILABLE.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    receipt = make_receipt(
        receipt_number="SP-2026-000003",
        verification_token="FAILURE123456789",
    )

    storage = LocalStorage(
        base_path=tmp_path,
    )

    # Preserve the real storage implementation for all
    # operations except upload.
    original_upload = storage.upload

    async def failing_upload(
        *,
        path: str,
        content: bytes,
        content_type: str,
        overwrite: bool = False,
    ) -> str:
        raise RuntimeError(
            "Simulated storage upload failure",
        )

    storage.upload = failing_upload

    service, repository = build_receipt_service(
        receipt=receipt,
        storage=storage,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    with pytest.raises(
        RuntimeError,
        match="Simulated storage upload failure",
    ):
        await service.generate_receipt(
            receipt_id=receipt.id,
        )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------

    assert receipt.status == "FAILED"

    assert receipt.failure_reason is not None

    assert (
        "Simulated storage upload failure"
        in receipt.failure_reason
    )

    assert receipt.pdf_storage_path is None

    assert receipt.pdf_url is None

    assert repository.save_called is True

    assert repository.commit_called is True

    # ------------------------------------------------------
    # Restore
    # ------------------------------------------------------

    storage.upload = original_upload

    print(
        "\nReceiptService storage failure handling: OK"
    )