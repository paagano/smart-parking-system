"""
Storage Factory

Provides the application's configured storage implementation.

The rest of the application should request storage through
this factory rather than instantiating LocalStorage or
SupabaseStorage directly.

Supported backends:

- local
- supabase

The backend is selected using:

    STORAGE_BACKEND

from application settings.
"""

from __future__ import annotations

from app.config import settings
from app.storage.base import StorageService
from app.storage.local import LocalStorage
from app.storage.supabase import SupabaseStorage


# ==========================================================
# Storage Factory
# ==========================================================


def get_storage() -> StorageService:
    """
    Return the configured application storage implementation.

    The implementation is selected using the STORAGE_BACKEND
    application setting.

    Supported values:

        local
        supabase

    Returns:
        Configured StorageService implementation.

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
        return SupabaseStorage()

    # ------------------------------------------------------
    # Unsupported Backend
    # ------------------------------------------------------

    raise ValueError(
        f"Unsupported STORAGE_BACKEND: '{settings.STORAGE_BACKEND}'. "
        "Supported values are: 'local' or 'supabase'."
    )


# ==========================================================
# Singleton-style Accessor
# ==========================================================

_storage_service: StorageService | None = None


def storage_service() -> StorageService:
    """
    Return the application's configured storage service.

    The storage implementation is initialized once and reused
    for the lifetime of the application process.

    Returns:
        Configured StorageService instance.
    """

    global _storage_service

    if _storage_service is None:
        _storage_service = get_storage()

    return _storage_service