"""
Local Storage Implementation

Provides filesystem-based storage for local development and
environments where cloud object storage is not required.

This implementation conforms to the StorageService abstraction,
allowing it to be replaced transparently by SupabaseStorage.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.config import settings
from app.storage.base import StorageService


class LocalStorage(StorageService):
    """
    Filesystem-based storage provider.

    Files are stored underneath the configured LOCAL_STORAGE_PATH.

    Example:

        LOCAL_STORAGE_PATH=storage

    A receipt stored at:

        payments/2026/08/RCPT-001.pdf

    will physically exist at:

        backend/storage/payments/2026/08/RCPT-001.pdf

    The corresponding application URL is:

        /storage/payments/2026/08/RCPT-001.pdf
    """

    # ==========================================================
    # Initialization
    # ==========================================================

    def __init__(
        self,
        base_path: str | Path | None = None,
        url_prefix: str = "/storage",
    ) -> None:
        """
        Initialize LocalStorage.

        Args:
            base_path:
                Root directory used for storing files.

                If omitted, LOCAL_STORAGE_PATH from application
                settings is used.

            url_prefix:
                URL prefix through which the application exposes
                local storage files.
        """

        configured_path = (
            base_path
            if base_path is not None
            else settings.LOCAL_STORAGE_PATH
        )

        self.base_path = Path(
            configured_path,
        ).expanduser().resolve()

        self.url_prefix = (
            "/" + url_prefix.strip("/")
        )

        self.base_path.mkdir(
            parents=True,
            exist_ok=True,
        )

    # ==========================================================
    # Path Handling
    # ==========================================================

    def _resolve_path(
        self,
        path: str,
    ) -> Path:
        """
        Resolve a storage-relative path safely.

        Prevents path traversal outside the configured storage
        directory.

        Args:
            path:
                Storage-relative object path.

        Returns:
            Absolute filesystem path.

        Raises:
            ValueError:
                If the supplied path is invalid or attempts to
                escape the storage root.
        """

        if not path:
            raise ValueError(
                "Storage path cannot be empty."
            )

        normalized_path = path.replace(
            "\\",
            "/",
        ).strip("/")

        if not normalized_path:
            raise ValueError(
                "Storage path cannot be empty."
            )

        relative_path = Path(
            normalized_path,
        )

        if relative_path.is_absolute():
            raise ValueError(
                "Storage path must be relative."
            )

        resolved_path = (
            self.base_path / relative_path
        ).resolve()

        try:
            resolved_path.relative_to(
                self.base_path,
            )
        except ValueError as exc:
            raise ValueError(
                "Storage path attempts to escape "
                "the configured storage directory."
            ) from exc

        return resolved_path

    def _relative_path(
        self,
        path: str,
    ) -> str:
        """
        Normalize a storage path for URL generation.

        Returns:
            POSIX-style relative storage path.
        """

        normalized_path = path.replace(
            "\\",
            "/",
        ).strip("/")

        if not normalized_path:
            raise ValueError(
                "Storage path cannot be empty."
            )

        # Resolve first so URL generation benefits from the
        # same path traversal protection as filesystem access.
        self._resolve_path(
            normalized_path,
        )

        return normalized_path

    # ==========================================================
    # Upload
    # ==========================================================

    async def upload(
        self,
        *,
        path: str,
        content: bytes,
        content_type: str,
        overwrite: bool = False,
    ) -> str:
        """
        Store binary content on the local filesystem.

        Args:
            path:
                Storage-relative object path.

            content:
                Binary file contents.

            content_type:
                MIME type of the object.

                The local filesystem does not require this value,
                but it is accepted to maintain compatibility with
                other storage providers.

            overwrite:
                Whether an existing file may be replaced.

        Returns:
            Storage-relative path of the stored object.

        Raises:
            FileExistsError:
                If the file already exists and overwrite=False.
        """

        del content_type

        file_path = self._resolve_path(
            path,
        )

        if (
            file_path.exists()
            and not overwrite
        ):
            raise FileExistsError(
                f"Storage object already exists: {path}"
            )

        file_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        await asyncio.to_thread(
            self._write_file,
            file_path,
            content,
        )

        return self._relative_path(
            path,
        )

    @staticmethod
    def _write_file(
        file_path: Path,
        content: bytes,
    ) -> None:
        """
        Synchronous filesystem write executed in a worker thread.
        """

        file_path.write_bytes(
            content,
        )

    # ==========================================================
    # Download
    # ==========================================================

    async def download(
        self,
        *,
        path: str,
    ) -> bytes:
        """
        Download an object from local storage.

        Args:
            path:
                Storage-relative object path.

        Returns:
            Binary contents of the stored object.

        Raises:
            FileNotFoundError:
                If the object does not exist.
        """

        file_path = self._resolve_path(
            path,
        )

        if not file_path.is_file():
            raise FileNotFoundError(
                f"Storage object not found: {path}"
            )

        return await asyncio.to_thread(
            file_path.read_bytes,
        )

    # ==========================================================
    # Delete
    # ==========================================================

    async def delete(
        self,
        *,
        path: str,
    ) -> None:
        """
        Delete an object from local storage.

        Args:
            path:
                Storage-relative object path.

        Raises:
            FileNotFoundError:
                If the object does not exist.
        """

        file_path = self._resolve_path(
            path,
        )

        if not file_path.is_file():
            raise FileNotFoundError(
                f"Storage object not found: {path}"
            )

        await asyncio.to_thread(
            file_path.unlink,
        )

    # ==========================================================
    # Exists
    # ==========================================================

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
            True if the object exists as a file.
        """

        file_path = self._resolve_path(
            path,
        )

        return await asyncio.to_thread(
            file_path.is_file,
        )

    # ==========================================================
    # URL
    # ==========================================================

    async def get_url(
        self,
        *,
        path: str,
    ) -> str:
        """
        Return the application URL for a locally stored object.

        The FastAPI application will later expose the configured
        local storage directory under the /storage URL prefix.

        Args:
            path:
                Storage-relative object path.

        Returns:
            Application-relative URL.
        """

        normalized_path = self._relative_path(
            path,
        )

        return (
            f"{self.url_prefix}/"
            f"{normalized_path}"
        )

    # ==========================================================
    # Signed URL
    # ==========================================================

    async def get_signed_url(
        self,
        *,
        path: str,
        expires_in: int = 3600,
    ) -> str:
        """
        Return an access URL for a locally stored object.

        Local filesystem storage does not provide native signed
        URLs. For local development, the normal application URL
        is therefore returned.

        Args:
            path:
                Storage-relative object path.

            expires_in:
                Requested URL lifetime.

                Accepted for interface compatibility with cloud
                storage providers. It does not alter the local
                URL because local storage has no signed-URL
                mechanism.

        Returns:
            Application-relative URL.
        """

        if expires_in <= 0:
            raise ValueError(
                "expires_in must be greater than zero."
            )

        return await self.get_url(
            path=path,
        )