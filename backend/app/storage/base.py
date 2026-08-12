"""
Storage Abstraction

Defines the common contract for application storage providers.

The application must not depend directly on a specific storage
provider such as the local filesystem or Supabase.

Concrete implementations must implement this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class StorageService(ABC):
    """
    Abstract interface for application file storage.

    Concrete implementations may use:

    - Local filesystem
    - Supabase Storage
    - Other object storage providers in the future

    The rest of the application should interact only with this
    interface.
    """

    # ==========================================================
    # Upload
    # ==========================================================

    @abstractmethod
    async def upload(
        self,
        *,
        path: str,
        content: bytes,
        content_type: str,
        overwrite: bool = False,
    ) -> str:
        """
        Store binary content.

        Args:
            path:
                Storage-relative path where the file should be
                stored.

            content:
                Binary file content.

            content_type:
                MIME type of the file.

            overwrite:
                Whether an existing file may be replaced.

        Returns:
            Storage path of the stored object.
        """

        raise NotImplementedError

    # ==========================================================
    # Download
    # ==========================================================

    @abstractmethod
    async def download(
        self,
        *,
        path: str,
    ) -> bytes:
        """
        Download an object from storage.

        Args:
            path:
                Storage-relative object path.

        Returns:
            Binary contents of the stored object.
        """

        raise NotImplementedError

    # ==========================================================
    # Delete
    # ==========================================================

    @abstractmethod
    async def delete(
        self,
        *,
        path: str,
    ) -> None:
        """
        Delete an object from storage.

        Args:
            path:
                Storage-relative object path.
        """

        raise NotImplementedError

    # ==========================================================
    # Exists
    # ==========================================================

    @abstractmethod
    async def exists(
        self,
        *,
        path: str,
    ) -> bool:
        """
        Determine whether an object exists.

        Args:
            path:
                Storage-relative object path.

        Returns:
            True if the object exists, otherwise False.
        """

        raise NotImplementedError

    # ==========================================================
    # URL
    # ==========================================================

    @abstractmethod
    async def get_url(
        self,
        *,
        path: str,
    ) -> str:
        """
        Return a URL through which the stored object can be
        accessed.

        Implementations may return:

        - A local application URL
        - A public Supabase URL
        - Another provider-specific URL

        Args:
            path:
                Storage-relative object path.

        Returns:
            URL for accessing the object.
        """

        raise NotImplementedError

    # ==========================================================
    # Signed URL
    # ==========================================================

    @abstractmethod
    async def get_signed_url(
        self,
        *,
        path: str,
        expires_in: int = 3600,
    ) -> str:
        """
        Return a temporary URL for accessing a stored object.

        This method is particularly important for private object
        storage, such as private Supabase Storage buckets.

        Local storage implementations may return their normal
        application URL because local files do not require
        provider-level signed access.

        Args:
            path:
                Storage-relative object path.

            expires_in:
                Number of seconds for which the generated URL
                should remain valid.

        Returns:
            Temporary URL for accessing the stored object.

        Raises:
            ValueError:
                If expires_in is less than or equal to zero.
        """

        if expires_in <= 0:
            raise ValueError("expires_in must be greater than zero")

        raise NotImplementedError