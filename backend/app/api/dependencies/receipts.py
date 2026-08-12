"""
Receipt Service Dependencies

Provides FastAPI Dependency Injection (DI) for the Receipt
Service and its required dependencies.

The Receipt Service coordinates:

- Receipt persistence
- PDF generation
- File storage
- Receipt notifications

Dependency responsibilities:

    Database Session
        ↓
    ReceiptRepository
        ↓
    ReceiptService
        ├── ReceiptPDFService
        ├── StorageService
        └── NotificationService

Business logic remains inside ReceiptService.

Persistence remains inside ReceiptRepository.

Storage implementation remains hidden behind the
StorageService abstraction.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.dependencies.notifications import (
    NotificationServiceDep,
)

from app.api.dependencies.repositories import (
    DbSession,
)

from app.api.dependencies.repositories import (
    ReceiptRepositoryDep,
)

from app.services.receipt_pdf_service import (
    ReceiptPDFService,
)

from app.services.receipt_service import (
    ReceiptService,
)

from app.storage import (
    StorageService,
    storage_service,
)


# ==========================================================
# Receipt Repository Dependency
# ==========================================================
#
# ReceiptRepositoryDep is imported from the repository
# dependency module.
#
# The repository itself is responsible only for persistence.
#


# ==========================================================
# Storage Service Dependency
# ==========================================================


def get_storage_service() -> StorageService:
    """
    Return the application's configured storage service.

    The actual implementation is selected by the storage
    factory based on STORAGE_BACKEND.

    Possible implementations include:

        LocalStorage
        SupabaseStorage

    Returns:
        Configured StorageService instance.
    """

    return storage_service()


StorageServiceDep = Annotated[
    StorageService,
    Depends(get_storage_service),
]


# ==========================================================
# Receipt PDF Service Dependency
# ==========================================================


def get_receipt_pdf_service() -> ReceiptPDFService:
    """
    Return a ReceiptPDFService instance.

    ReceiptPDFService is responsible only for generating the
    customer-facing receipt PDF.

    It does not:

    - persist receipts
    - access PostgreSQL
    - upload files
    - send notifications
    """

    return ReceiptPDFService()


ReceiptPDFServiceDep = Annotated[
    ReceiptPDFService,
    Depends(get_receipt_pdf_service),
]


# ==========================================================
# Receipt Service
# ==========================================================


def get_receipt_service(
    db: DbSession,
    repository: ReceiptRepositoryDep,
    storage_service: StorageServiceDep,
    pdf_service: ReceiptPDFServiceDep,
    notification_service: NotificationServiceDep,
) -> ReceiptService:
    """
    Return a fully configured ReceiptService instance.

    Dependencies
    ------------
    db:
        Active SQLAlchemy AsyncSession.

    repository:
        ReceiptRepository responsible for receipt persistence.

    storage_service:
        Configured StorageService implementation. This may be
        LocalStorage or SupabaseStorage depending on
        STORAGE_BACKEND.

    pdf_service:
        ReceiptPDFService responsible for PDF generation.

    notification_service:
        NotificationService responsible for receipt-related
        customer notifications.

    Returns
    -------
    ReceiptService
        Fully constructed ReceiptService.
    """

    return ReceiptService(
        db=db,
        repository=repository,
        storage_service=storage_service,
        pdf_service=pdf_service,
        notification_service=notification_service,
    )


# ==========================================================
# Dependency Alias
# ==========================================================


ReceiptServiceDep = Annotated[
    ReceiptService,
    Depends(get_receipt_service),
]