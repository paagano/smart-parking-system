"""
ReceiptService -> ReceiptPDFService -> LocalStorage -> PostgreSQL
Integration Test

This test exercises the real receipt generation pipeline:

    PaymentTransaction
            |
            v
    ReceiptService
            |
            +------------------+
            |                  |
            v                  v
    ReceiptRepository   ReceiptPDFService
            |                  |
            |                  v
            |              PDF bytes
            |                  |
            |                  v
            |            LocalStorage
            |                  |
            |                  v
            |             Stored PDF
            |
            v
       PostgreSQL

What this test uses for REAL:

- PostgreSQL test database
- SQLAlchemy AsyncSession
- PaymentTransaction model
- Receipt model
- ReceiptRepository
- ReceiptService
- ReceiptPDFService
- LocalStorage
- Receipt persistence
- PDF generation
- PDF storage
- PDF download

What this test does NOT use:

- Mock ReceiptRepository
- Mock ReceiptPDFService
- Mock StorageService
- Supabase
- NotificationService
- Production database

The LocalStorage instance uses a temporary filesystem directory so
the test does not pollute the application's normal storage directory.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
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
    Currency,
    PaymentMethod,
    PaymentProvider,
    PaymentPurpose,
    PaymentStatus,
    PaymentType,
    ReceiptStatus,
    ReceiptType,
)

from app.models.payment_transaction import PaymentTransaction
from app.models.receipt import Receipt

from app.repositories.receipt_repository import ReceiptRepository

from app.services.receipt_pdf_service import ReceiptPDFService
from app.services.receipt_service import ReceiptService

from app.storage.local import LocalStorage


# ==========================================================
# Test Database
# ==========================================================


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """
    Create a real asynchronous PostgreSQL test database session.

    IMPORTANT:
    This uses TEST_DATABASE_URL and therefore does not use the
    application's normal development database URL.
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
# Payment Factory
# ==========================================================


def build_payment() -> PaymentTransaction:
    """
    Build a real PaymentTransaction suitable for receipt generation.

    No customer is attached intentionally.

    This allows the integration test to focus strictly on:

        PaymentTransaction
            ->
        ReceiptService
            ->
        ReceiptPDFService
            ->
        LocalStorage
            ->
        PostgreSQL

    ReceiptService skips receipt notifications when customer_id
    is None.
    """

    unique_id = uuid4().hex[:12].upper()

    return PaymentTransaction(
        transaction_number=f"IT-{unique_id}",

        # ------------------------------------------------------
        # Payment references
        # ------------------------------------------------------

        reservation_id=None,
        parking_session_id=None,
        customer_id=None,
        parent_transaction_id=None,

        # ------------------------------------------------------
        # Payment identity/details
        # ------------------------------------------------------

        payment_type=PaymentType.PAYMENT,
        payment_purpose=PaymentPurpose.PARKING_SESSION,
        payment_method=PaymentMethod.MPESA,
        payment_provider=PaymentProvider.SAFARICOM,
        currency=Currency.KES,

        # ------------------------------------------------------
        # Financial values
        # ------------------------------------------------------

        subtotal_amount=Decimal("400.00"),
        discount_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("400.00"),

        # ------------------------------------------------------
        # Provider/reference information
        # ------------------------------------------------------

        external_reference=f"EXT-{unique_id}",
        receipt_number=f"QK{unique_id}",
        provider_transaction_id=f"MPESA-{unique_id}",
        provider_status_message="Integration test payment",
        provider_response={
            "test": True,
            "provider": "SAFARICOM",
            "reference": unique_id,
        },

        # ------------------------------------------------------
        # Payer snapshot
        # ------------------------------------------------------

        payer_name="SmartPark Integration Test",
        payer_phone="0712345678",
        payer_email="smartpark.integration@test.local",

        # ------------------------------------------------------
        # Payment status
        # ------------------------------------------------------

        status=PaymentStatus.SUCCESSFUL,
        paid_at=datetime.now(timezone.utc),
        notes="Automated receipt integration test",

        # ------------------------------------------------------
        # Optional financial/audit fields
        # ------------------------------------------------------

        balance_after=None,
        is_reconciled=False,
        idempotency_key=f"receipt-integration-{unique_id}",
        loyalty_points_earned=0,
        loyalty_points_redeemed=0,
    )


# ==========================================================
# Integration Test
# ==========================================================


@pytest.mark.asyncio
async def test_receipt_service_pdf_storage_postgresql_integration(
    db_session: AsyncSession,
):
    """
    Exercise the complete real receipt generation pipeline.

    Expected workflow:

        1. Persist real PaymentTransaction
        2. Construct real ReceiptRepository
        3. Construct real ReceiptPDFService
        4. Construct real LocalStorage
        5. Construct real ReceiptService
        6. Create real Receipt through ReceiptService
        7. Generate real PDF
        8. Store real PDF using LocalStorage
        9. Update real Receipt in PostgreSQL
        10. Reload Receipt from PostgreSQL
        11. Download PDF through ReceiptService
        12. Verify PDF contents
        13. Clean up database and temporary storage
    """

    payment = build_payment()

    receipt: Receipt | None = None

    # ==========================================================
    # Temporary local storage
    # ==========================================================

    with TemporaryDirectory(
        prefix="smartpark_receipt_test_",
    ) as temporary_directory:

        storage_root = Path(
            temporary_directory
        )

        storage_service = LocalStorage(
            base_path=storage_root,
        )

        # ======================================================
        # Real application services
        # ======================================================

        repository = ReceiptRepository(
            db_session,
        )

        pdf_service = ReceiptPDFService()

        receipt_service = ReceiptService(
            db=db_session,
            repository=repository,
            storage_service=storage_service,
            pdf_service=pdf_service,
            notification_service=None,
        )

        # ======================================================
        # Step 1: Persist REAL PaymentTransaction
        # ======================================================

        db_session.add(payment)

        await db_session.commit()

        await db_session.refresh(
            payment,
        )

        assert payment.id is not None

        print(
            f"\nPaymentTransaction created: ID={payment.id}"
        )

        # ======================================================
        # Step 2: Verify PaymentTransaction exists
        # ======================================================

        persisted_payment_result = await db_session.execute(
            select(PaymentTransaction).where(
                PaymentTransaction.id == payment.id
            )
        )

        persisted_payment = (
            persisted_payment_result.scalar_one_or_none()
        )

        assert persisted_payment is not None

        assert (
            persisted_payment.status
            == PaymentStatus.SUCCESSFUL
        )

        assert (
            persisted_payment.total_amount
            == Decimal("400.00")
        )

        print(
            "PaymentTransaction PostgreSQL persistence: OK"
        )

        # ======================================================
        # Step 3: ReceiptService creates REAL Receipt
        # ======================================================

        receipt = await receipt_service.create_receipt(
            payment=payment,
        )

        assert receipt is not None

        assert receipt.id is not None

        assert (
            receipt.payment_transaction_id
            == payment.id
        )

        assert (
            receipt.receipt_type
            == ReceiptType.PAYMENT
        )

        assert (
            receipt.status
            == ReceiptStatus.PENDING
        )

        assert (
            receipt.total_amount
            == Decimal("400.00")
        )

        assert receipt.currency == "KES"

        assert receipt.verification_token

        print(
            f"Receipt created: {receipt.receipt_number}"
        )

        print(
            "Receipt PostgreSQL creation: OK"
        )

        # ======================================================
        # Step 4: Verify ReceiptRepository retrieval
        # ======================================================

        repository_receipt = (
            await repository.get_by_id(
                receipt.id,
            )
        )

        assert repository_receipt is not None

        assert (
            repository_receipt.id
            == receipt.id
        )

        assert (
            repository_receipt.payment_transaction_id
            == payment.id
        )

        print(
            "ReceiptRepository retrieval: OK"
        )

        # ======================================================
        # Step 5: Generate REAL PDF and store it
        # ======================================================

        generated_receipt = (
            await receipt_service.generate_receipt(
                receipt_id=receipt.id,
            )
        )

        assert generated_receipt is not None

        assert (
            generated_receipt.id
            == receipt.id
        )

        # ======================================================
        # Step 6: Verify Receipt lifecycle
        # ======================================================

        assert (
            generated_receipt.status
            == ReceiptStatus.AVAILABLE
        )

        assert (
            generated_receipt.generated_at
            is not None
        )

        assert (
            generated_receipt.available_at
            is not None
        )

        assert (
            generated_receipt.failure_reason
            is None
        )

        print(
            "Receipt lifecycle PENDING -> AVAILABLE: OK"
        )

        # ======================================================
        # Step 7: Verify storage path
        # ======================================================

        assert (
            generated_receipt.pdf_storage_path
            is not None
        )

        expected_prefix = "receipts/"

        assert (
            generated_receipt.pdf_storage_path.startswith(
                expected_prefix
            )
        )

        assert (
            generated_receipt.pdf_storage_path.endswith(
                ".pdf"
            )
        )

        print(
            "Receipt storage path generation: OK"
        )

        # ======================================================
        # Step 8: Verify physical LocalStorage file
        # ======================================================

        physical_pdf_path = (
            storage_root
            / generated_receipt.pdf_storage_path
        )

        assert physical_pdf_path.exists()

        assert physical_pdf_path.is_file()

        assert (
            physical_pdf_path.stat().st_size
            > 0
        )

        print(
            "LocalStorage physical PDF file: OK"
        )

        print(
            f"Stored PDF: {physical_pdf_path}"
        )

        # ======================================================
        # Step 9: Verify stored PDF through StorageService
        # ======================================================

        stored_pdf_bytes = (
            await storage_service.download(
                path=generated_receipt.pdf_storage_path,
            )
        )

        assert isinstance(
            stored_pdf_bytes,
            bytes,
        )

        assert len(
            stored_pdf_bytes
        ) > 0

        assert stored_pdf_bytes.startswith(
            b"%PDF"
        )

        print(
            "LocalStorage PDF download: OK"
        )

        # ======================================================
        # Step 10: Verify PDF access URL
        # ======================================================

        assert (
            generated_receipt.pdf_url
            is not None
        )

        assert (
            generated_receipt.pdf_url.startswith(
                "/storage/"
            )
        )

        print(
            f"PDF URL: {generated_receipt.pdf_url}"
        )

        print(
            "Receipt PDF URL generation: OK"
        )

        # ======================================================
        # Step 11: Verify ReceiptService download
        # ======================================================

        downloaded_pdf = (
            await receipt_service.download_receipt_pdf(
                receipt_id=generated_receipt.id,
            )
        )

        assert isinstance(
            downloaded_pdf,
            bytes,
        )

        assert len(
            downloaded_pdf
        ) > 0

        assert downloaded_pdf.startswith(
            b"%PDF"
        )

        assert (
            downloaded_pdf
            == stored_pdf_bytes
        )

        print(
            "ReceiptService PDF download: OK"
        )

        # ======================================================
        # Step 12: Verify ReceiptService access URL
        # ======================================================

        receipt_url = (
            await receipt_service.get_receipt_url(
                receipt_id=generated_receipt.id,
            )
        )

        assert receipt_url

        assert receipt_url.startswith(
            "/storage/"
        )

        print(
            "ReceiptService receipt URL: OK"
        )

        # ======================================================
        # Step 13: Reload Receipt from PostgreSQL
        #
        # IMPORTANT:
        #
        # Do NOT call:
        #
        #     db_session.expire_all()
        #
        # before accessing generated_receipt.id.
        #
        # With AsyncSession, expiring ORM attributes can cause
        # SQLAlchemy to perform implicit asynchronous IO during
        # normal attribute access, resulting in MissingGreenlet.
        #
        # Instead, perform a fresh repository query.
        # ======================================================

        persisted_receipt = (
            await repository.get_by_id(
                generated_receipt.id,
            )
        )

        assert persisted_receipt is not None

        assert (
            persisted_receipt.id
            == generated_receipt.id
        )

        print(
            "Receipt PostgreSQL reload: OK"
        )

        # ======================================================
        # Step 14: Verify persisted lifecycle
        # ======================================================

        assert (
            persisted_receipt.status
            == ReceiptStatus.AVAILABLE
        )

        assert (
            persisted_receipt.pdf_storage_path
            == generated_receipt.pdf_storage_path
        )

        assert (
            persisted_receipt.pdf_url
            == generated_receipt.pdf_url
        )

        assert (
            persisted_receipt.generated_at
            is not None
        )

        assert (
            persisted_receipt.available_at
            is not None
        )

        assert (
            persisted_receipt.failure_reason
            is None
        )

        print(
            "PostgreSQL Receipt update: OK"
        )

        # ======================================================
        # Step 15: Verify financial snapshot
        # ======================================================

        assert (
            persisted_receipt.payment_transaction_id
            == payment.id
        )

        assert (
            persisted_receipt.subtotal_amount
            == Decimal("400.00")
        )

        assert (
            persisted_receipt.discount_amount
            == Decimal("0.00")
        )

        assert (
            persisted_receipt.tax_amount
            == Decimal("0.00")
        )

        assert (
            persisted_receipt.total_amount
            == Decimal("400.00")
        )

        assert (
            persisted_receipt.currency
            == "KES"
        )

        assert (
            persisted_receipt.payment_method
            == "MPESA"
        )

        assert (
            persisted_receipt.payment_provider
            == "SAFARICOM"
        )

        assert (
            persisted_receipt.provider_receipt_number
            == payment.receipt_number
        )

        print(
            "Receipt financial snapshot: OK"
        )

        # ======================================================
        # Step 16: Verify customer/payment snapshot
        # ======================================================

        assert (
            persisted_receipt.customer_name
            == payment.payer_name
        )

        assert (
            persisted_receipt.customer_phone
            == payment.payer_phone
        )

        assert (
            persisted_receipt.customer_email
            == payment.payer_email
        )

        print(
            "Receipt customer snapshot: OK"
        )

        # ======================================================
        # Step 17: Verify receipt identity/token
        # ======================================================

        assert (
            persisted_receipt.receipt_number
        )

        assert (
            persisted_receipt.receipt_number.startswith(
                "RCP-"
            )
        )

        assert (
            persisted_receipt.verification_token
        )

        assert (
            len(
                persisted_receipt.verification_token
            )
            > 20
        )

        print(
            "Receipt identity and verification token: OK"
        )

        # ======================================================
        # Step 18: Verify one-to-one relationship
        # ======================================================

        repository_lookup = (
            await repository.get_by_payment_transaction_id(
                payment.id,
            )
        )

        assert repository_lookup is not None

        assert (
            repository_lookup.id
            == persisted_receipt.id
        )

        print(
            "PaymentTransaction -> Receipt relationship: OK"
        )

        # ======================================================
        # Step 19: Cleanup physical PDF
        # ======================================================

        await storage_service.delete(
            path=persisted_receipt.pdf_storage_path,
        )

        assert not physical_pdf_path.exists()

        print(
            "LocalStorage cleanup: OK"
        )

        # ======================================================
        # Step 20: Cleanup database
        #
        # Receipt must be deleted first because it has a
        # RESTRICT foreign key to PaymentTransaction.
        # ======================================================

        await db_session.delete(
            persisted_receipt,
        )

        await db_session.delete(
            payment,
        )

        await db_session.commit()

        print(
            "Integration test database cleanup: OK"
        )

        # ======================================================
        # Step 21: Final PostgreSQL verification
        # ======================================================

        deleted_receipt_result = (
            await db_session.execute(
                select(Receipt).where(
                    Receipt.id
                    == generated_receipt.id
                )
            )
        )

        deleted_receipt = (
            deleted_receipt_result.scalar_one_or_none()
        )

        assert deleted_receipt is None

        deleted_payment_result = (
            await db_session.execute(
                select(PaymentTransaction).where(
                    PaymentTransaction.id
                    == payment.id
                )
            )
        )

        deleted_payment = (
            deleted_payment_result.scalar_one_or_none()
        )

        assert deleted_payment is None

        print(
            "\n"
            "====================================================\n"
            "ReceiptService -> PDF -> LocalStorage -> PostgreSQL\n"
            "INTEGRATION TEST: PASSED\n"
            "===================================================="
        )