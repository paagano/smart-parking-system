"""
ReceiptService dependency construction test.

This test does NOT:
- connect to PostgreSQL
- generate a PDF
- upload anything to Supabase
- create notifications

It only verifies that ReceiptService can be constructed
with its required dependencies.
"""

from unittest.mock import Mock

from app.services.receipt_service import ReceiptService


def test_receipt_service_dependency_construction():
    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    db = Mock(name="AsyncSession")

    repository = Mock(
        name="ReceiptRepository",
    )

    storage_service = Mock(
        name="StorageService",
    )

    pdf_service = Mock(
        name="ReceiptPDFService",
    )

    notification_service = Mock(
        name="NotificationService",
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    service = ReceiptService(
        db=db,
        repository=repository,
        storage_service=storage_service,
        pdf_service=pdf_service,
        notification_service=notification_service,
    )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------

    assert service.db is db

    assert service.repository is repository

    assert (
        service.storage_service
        is storage_service
    )

    assert (
        service.pdf_service
        is pdf_service
    )

    assert (
        service.notification_service
        is notification_service
    )

    print(
        "ReceiptService dependency construction: OK"
    )

def test_receipt_service_without_notification_service():
    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    db = Mock(name="AsyncSession")

    repository = Mock(
        name="ReceiptRepository",
    )

    storage_service = Mock(
        name="StorageService",
    )

    pdf_service = Mock(
        name="ReceiptPDFService",
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    service = ReceiptService(
        db=db,
        repository=repository,
        storage_service=storage_service,
        pdf_service=pdf_service,
    )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------

    assert service.db is db

    assert service.repository is repository

    assert (
        service.storage_service
        is storage_service
    )

    assert (
        service.pdf_service
        is pdf_service
    )

    assert (
        service.notification_service
        is None
    )

    print(
        "ReceiptService optional notification dependency: OK"
    )