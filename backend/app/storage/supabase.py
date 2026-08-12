"""
Supabase Storage Implementation

Provides cloud-based file storage using Supabase Storage.

This implementation conforms to the StorageService abstraction,
allowing the application to switch between local filesystem
storage and Supabase Storage without changing the business logic.

The receipts bucket is expected to be private in production.
Private receipt files should therefore be accessed through
temporary signed URLs.
"""

from __future__ import annotations

import asyncio
from pathlib import PurePosixPath
from typing import Any

from typing import Any

from supabase import create_client

from app.config import settings
from app.storage.base import StorageService


class SupabaseStorage(StorageService):
    """
    Supabase Storage provider.

    Configuration is loaded from application settings:

        SUPABASE_URL
        SUPABASE_KEY
        SUPABASE_BUCKET
        SUPABASE_PUBLIC_BUCKET

    Example storage path:

        payments/2026/08/RCPT-20260811-001.pdf

    The path is relative to the configured Supabase bucket.
    """

    # ==========================================================
    # Initialization
    # ==========================================================

    def __init__(
        self,
        client: Any | None = None,
        bucket: str | None = None,
    ) -> None:
        """
        Initialize Supabase Storage.

        Args:
            client:
                Optional existing Supabase client.

                Supplying a client is useful for testing and
                dependency injection.

            bucket:
                Optional bucket override.

                If omitted, SUPABASE_BUCKET from settings is used.
        """

        self.bucket_name = (
            bucket
            or settings.SUPABASE_BUCKET
        )

        if not self.bucket_name:
            raise ValueError(
                "SUPABASE_BUCKET must be configured."
            )

        if client is not None:
            self.client = client
        else:
            self.client = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_KEY,
            )

        self.bucket = self.client.storage.from_(
            self.bucket_name,
        )

    # ==========================================================
    # Path Handling
    # ==========================================================

    @staticmethod
    def _normalize_path(
        path: str,
    ) -> str:
        """
        Normalize and validate a storage-relative path.

        Prevents absolute paths and path traversal.

        Args:
            path:
                Storage-relative object path.

        Returns:
            Normalized POSIX-style storage path.

        Raises:
            ValueError:
                If the path is invalid or attempts to escape the
                storage namespace.
        """

        if not path:
            raise ValueError(
                "Storage path cannot be empty."
            )

        normalized = path.replace(
            "\\",
            "/",
        ).strip("/")

        if not normalized:
            raise ValueError(
                "Storage path cannot be empty."
            )

        pure_path = PurePosixPath(
            normalized,
        )

        if pure_path.is_absolute():
            raise ValueError(
                "Storage path must be relative."
            )

        parts = pure_path.parts

        if ".." in parts:
            raise ValueError(
                "Storage path cannot contain '..'."
            )

        if "." in parts:
            raise ValueError(
                "Storage path cannot contain '.' path segments."
            )

        return "/".join(parts)

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
        Upload binary content to Supabase Storage.

        Args:
            path:
                Storage-relative object path.

            content:
                Binary file contents.

            content_type:
                MIME type of the object.

            overwrite:
                Whether an existing object may be replaced.

        Returns:
            Storage-relative path of the uploaded object.

        Raises:
            FileExistsError:
                If the object already exists and overwrite=False.

            Exception:
                If Supabase rejects the upload.
        """

        normalized_path = self._normalize_path(
            path,
        )

        if not overwrite:
            already_exists = await self.exists(
                path=normalized_path,
            )

            if already_exists:
                raise FileExistsError(
                    f"Storage object already exists: "
                    f"{normalized_path}"
                )

        file_options: dict[str, Any] = {
            "content-type": content_type,
            "cache-control": "3600",
            "upsert": "true" if overwrite else "false",
        }

        await asyncio.to_thread(
            self.bucket.upload,
            normalized_path,
            content,
            file_options,
        )

        return normalized_path

    # ==========================================================
    # Download
    # ==========================================================

    async def download(
        self,
        *,
        path: str,
    ) -> bytes:
        """
        Download an object from Supabase Storage.

        This works with private buckets when the configured
        Supabase client has the necessary storage permissions.

        Args:
            path:
                Storage-relative object path.

        Returns:
            Binary contents of the stored object.

        Raises:
            FileNotFoundError:
                If the object does not exist.
        """

        normalized_path = self._normalize_path(
            path,
        )

        try:
            content = await asyncio.to_thread(
                self.bucket.download,
                normalized_path,
            )
        except Exception as exc:
            raise FileNotFoundError(
                f"Storage object could not be downloaded: "
                f"{normalized_path}"
            ) from exc

        if content is None:
            raise FileNotFoundError(
                f"Storage object not found: "
                f"{normalized_path}"
            )

        return bytes(content)

    # ==========================================================
    # Delete
    # ==========================================================

    async def delete(
        self,
        *,
        path: str,
    ) -> None:
        """
        Delete an object from Supabase Storage.

        Args:
            path:
                Storage-relative object path.

        Raises:
            FileNotFoundError:
                If the object does not exist.
        """

        normalized_path = self._normalize_path(
            path,
        )

        if not await self.exists(
            path=normalized_path,
        ):
            raise FileNotFoundError(
                f"Storage object not found: "
                f"{normalized_path}"
            )

        await asyncio.to_thread(
            self.bucket.remove,
            [normalized_path],
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
        Determine whether an object exists in Supabase Storage.

        Uses the Storage list API rather than downloading the
        object merely to determine whether it exists.

        Args:
            path:
                Storage-relative object path.

        Returns:
            True if the object exists, otherwise False.
        """

        normalized_path = self._normalize_path(
            path,
        )

        pure_path = PurePosixPath(
            normalized_path,
        )

        parent_path = str(
            pure_path.parent,
        )

        if parent_path == ".":
            parent_path = ""

        filename = pure_path.name

        try:
            results = await asyncio.to_thread(
                self.bucket.list,
                parent_path,
                {
                    "limit": 100,
                    "offset": 0,
                    "search": filename,
                },
            )
        except Exception:
            return False

        if not results:
            return False

        for item in results:
            if not isinstance(item, dict):
                continue

            if item.get("name") == filename:
                return True

        return False

    # ==========================================================
    # URL
    # ==========================================================

    async def get_url(
        self,
        *,
        path: str,
    ) -> str:
        """
        Return a URL for the stored object.

        For a public bucket, this returns the Supabase public URL.

        For a private bucket, this method returns the Supabase
        public URL structure but does NOT make the object publicly
        accessible.

        Private receipt access should use get_signed_url().

        Args:
            path:
                Storage-relative object path.

        Returns:
            Supabase object URL.
        """

        normalized_path = self._normalize_path(
            path,
        )

        if not settings.SUPABASE_PUBLIC_BUCKET:
            raise ValueError(
                "Cannot return a public URL for a private "
                "Supabase bucket. Use get_signed_url() instead."
            )

        return await asyncio.to_thread(
            self.bucket.get_public_url,
            normalized_path,
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
        Generate a temporary signed URL for a stored object.

        This is the preferred access mechanism for SmartPark
        receipts because the receipts bucket is private.

        Args:
            path:
                Storage-relative object path.

            expires_in:
                Number of seconds for which the signed URL remains
                valid.

        Returns:
            Temporary signed URL.

        Raises:
            ValueError:
                If expires_in is less than or equal to zero.
        """

        if expires_in <= 0:
            raise ValueError(
                "expires_in must be greater than zero."
            )

        normalized_path = self._normalize_path(
            path,
        )

        response = await asyncio.to_thread(
            self.bucket.create_signed_url,
            normalized_path,
            expires_in,
        )

        if not response:
            raise RuntimeError(
                "Supabase did not return a signed URL."
            )

        # Current supabase-py returns a mapping containing
        # the signed URL. Keep the extraction defensive so that
        # minor response-shape differences do not leak into the
        # rest of the application.
        if isinstance(response, dict):
            signed_url = response.get(
                "signedURL",
            ) or response.get(
                "signedUrl",
            )

            if signed_url:
                return str(signed_url)

        # Some client versions may expose the response through
        # an object rather than a plain dictionary.
        signed_url = getattr(
            response,
            "signed_url",
            None,
        )

        if signed_url:
            return str(signed_url)

        raise RuntimeError(
            "Supabase signed URL response did not contain "
            "a usable URL."
        )