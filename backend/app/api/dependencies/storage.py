"""
Storage Dependencies

Provides FastAPI Dependency Injection (DI) for storage services.

The application uses separate storage dependencies for different
file domains so that receipt storage and profile-picture storage
remain isolated.

Storage responsibilities:

    Receipt Files
        ↓
    Application Storage Bucket

    Profile Pictures
        ↓
    Profile Picture Storage Bucket

The underlying implementation remains hidden behind the
StorageService abstraction.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.config import settings
from app.storage import (
    StorageService,
    storage_service,
)
from app.storage.local import LocalStorage
from app.storage.supabase import SupabaseStorage


# ==========================================================
# General Application Storage
# ==========================================================


def get_storage_service() -> StorageService:
    """
    Return the application's configured storage service.

    This is the primary storage dependency used by existing
    application functionality such as receipt storage.

    The implementation is selected through STORAGE_BACKEND.

    Supported backends:

        local
        supabase

    Returns:
        Configured StorageService instance.
    """

    return storage_service()


StorageServiceDep = Annotated[
    StorageService,
    Depends(get_storage_service),
]


# ==========================================================
# Profile Picture Storage
# ==========================================================


def get_profile_picture_storage_service() -> StorageService:
    """
    Return the storage service dedicated to profile pictures.

    Profile pictures use a separate Supabase bucket from receipts
    to prevent profile-picture operations from affecting receipt
    storage.

    For local development, LocalStorage is used. Profile pictures
    are stored under the profile_pictures/ directory.

    For Supabase, a dedicated bucket is used through
    SUPABASE_PROFILE_PICTURE_BUCKET.

    The profile-picture Supabase bucket is configured as public
    independently of the receipt bucket so that profile-picture
    URLs can be returned directly to the frontend.

    Returns:
        StorageService implementation dedicated to profile
        pictures.

    Raises:
        ValueError:
            If STORAGE_BACKEND contains an unsupported value.
    """

    backend = settings.STORAGE_BACKEND.strip().lower()

    # ------------------------------------------------------
    # Local Storage
    # ------------------------------------------------------

    if backend == "local":
        return LocalStorage()

    # ------------------------------------------------------
    # Supabase Storage
    # ------------------------------------------------------

    if backend == "supabase":
        return SupabaseStorage(
            bucket=settings.SUPABASE_PROFILE_PICTURE_BUCKET,
            public_bucket=settings.SUPABASE_PROFILE_PICTURE_PUBLIC,
        )

    # ------------------------------------------------------
    # Unsupported Backend
    # ------------------------------------------------------

    raise ValueError(
        f"Unsupported STORAGE_BACKEND: "
        f"'{settings.STORAGE_BACKEND}'. "
        "Supported values are: 'local' or 'supabase'."
    )


ProfilePictureStorageServiceDep = Annotated[
    StorageService,
    Depends(get_profile_picture_storage_service),
]