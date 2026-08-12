"""
SmartPark Storage Package

Provides the application's storage abstraction and configured
storage service.
"""

from app.storage.base import StorageService
from app.storage.factory import get_storage, storage_service

__all__ = [
    "StorageService",
    "get_storage",
    "storage_service",
]