"""
QR Access Token Service.

Provides business logic for generating, validating,
resolving, activating, and deactivating temporary
QR access tokens.

QR tokens are intentionally opaque.

The raw token is never stored in the database.
Only its SHA-256 hash is persisted.

Transaction management is handled by this Service layer.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from app.models.enums import QRAccessPurpose
from app.models.qr_access_token import QRAccessToken
from app.repositories.qr_access_token_repository import (
    QRAccessTokenRepository,
)


class QRAccessTokenService:
    def __init__(
        self,
        repository: QRAccessTokenRepository,
    ) -> None:
        self.repository = repository

    @staticmethod
    def _generate_raw_token() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _normalize_token(token: str) -> str:
        return token.strip()

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    async def create_token(
        self,
        *,
        facility_id: int,
        purpose: QRAccessPurpose,
        expires_in_seconds: int = 300,
    ) -> tuple[QRAccessToken, str]:
        if facility_id <= 0:
            raise ValueError(
                "Facility ID must be greater than zero."
            )

        if expires_in_seconds <= 0:
            raise ValueError(
                "Token expiry must be greater than zero seconds."
            )

        raw_token = self._generate_raw_token()

        token_hash = self._hash_token(
            raw_token
        )

        expires_at = (
            self._utc_now()
            + timedelta(
                seconds=expires_in_seconds
            )
        )

        qr_access_token = QRAccessToken(
            token_hash=token_hash,
            facility_id=facility_id,
            purpose=purpose,
            expires_at=expires_at,
            is_active=True,
        )

        self.repository.db.add(
            qr_access_token
        )

        await self.repository.db.flush()

        await self.repository.db.commit()

        await self.repository.db.refresh(
            qr_access_token
        )

        return qr_access_token, raw_token

    async def get_token(
        self,
        token_id: int,
    ) -> QRAccessToken | None:
        return await self.repository.get_by_id(
            token_id
        )

    async def resolve_token(
        self,
        *,
        raw_token: str,
        facility_id: int,
        purpose: QRAccessPurpose,
    ) -> QRAccessToken:
        normalized_token = self._normalize_token(
            raw_token
        )

        if not normalized_token:
            raise ValueError(
                "QR token is required."
            )

        if facility_id <= 0:
            raise ValueError(
                "Facility ID must be greater than zero."
            )

        token_hash = self._hash_token(
            normalized_token
        )

        qr_access_token = (
            await self.repository.get_active_by_token_hash(
                token_hash
            )
        )

        if qr_access_token is None:
            raise ValueError(
                "QR token is invalid or inactive."
            )

        if qr_access_token.facility_id != facility_id:
            raise ValueError(
                "QR token does not belong to this facility."
            )

        if qr_access_token.purpose != purpose:
            raise ValueError(
                "QR token purpose does not match the requested operation."
            )

        if (
            qr_access_token.expires_at
            <= self._utc_now()
        ):
            raise ValueError(
                "QR token has expired."
            )

        return qr_access_token

    async def resolve_public_token(
        self,
        *,
        raw_token: str,
        purpose: QRAccessPurpose,
    ) -> QRAccessToken:
        """
        Resolve a QR access token for a public/mobile
        operation.

        The facility is obtained from the token itself.
        The client is never trusted to provide a facility ID.

        This method validates:
        - token presence
        - token existence
        - token active status
        - token purpose
        - token expiry
        """

        normalized_token = self._normalize_token(
            raw_token
        )

        if not normalized_token:
            raise ValueError(
                "QR token is required."
            )

        token_hash = self._hash_token(
            normalized_token
        )

        qr_access_token = (
            await self.repository.get_active_by_token_hash(
                token_hash
            )
        )

        if qr_access_token is None:
            raise ValueError(
                "QR token is invalid or inactive."
            )

        if qr_access_token.purpose != purpose:
            raise ValueError(
                "QR token purpose does not match the requested operation."
            )

        if (
            qr_access_token.expires_at
            <= self._utc_now()
        ):
            raise ValueError(
                "QR token has expired."
            )

        return qr_access_token

    async def deactivate_token(
        self,
        *,
        token_id: int,
        facility_id: int,
    ) -> QRAccessToken:
        qr_access_token = (
            await self.repository.get_by_id(
                token_id
            )
        )

        if qr_access_token is None:
            raise ValueError(
                "QR access token not found."
            )

        if qr_access_token.facility_id != facility_id:
            raise ValueError(
                "QR access token does not belong to this facility."
            )

        if not qr_access_token.is_active:
            return qr_access_token

        await self.repository.deactivate(
            qr_access_token
        )

        qr_access_token.updated_at = (
            self._utc_now()
        )

        await self.repository.db.flush()

        await self.repository.db.commit()

        await self.repository.db.refresh(
            qr_access_token
        )

        return qr_access_token

    async def activate_token(
        self,
        *,
        token_id: int,
        facility_id: int,
    ) -> QRAccessToken:
        qr_access_token = (
            await self.repository.get_by_id(
                token_id
            )
        )

        if qr_access_token is None:
            raise ValueError(
                "QR access token not found."
            )

        if qr_access_token.facility_id != facility_id:
            raise ValueError(
                "QR access token does not belong to this facility."
            )

        if (
            qr_access_token.expires_at
            <= self._utc_now()
        ):
            raise ValueError(
                "Expired QR tokens cannot be activated."
            )

        qr_access_token.is_active = True

        qr_access_token.updated_at = (
            self._utc_now()
        )

        await self.repository.db.flush()

        await self.repository.db.commit()

        await self.repository.db.refresh(
            qr_access_token
        )

        return qr_access_token

    async def get_facility_tokens(
        self,
        facility_id: int,
    ) -> list[QRAccessToken]:
        if facility_id <= 0:
            raise ValueError(
                "Facility ID must be greater than zero."
            )

        return await self.repository.get_all_by_facility(
            facility_id
        )

    async def get_active_facility_tokens(
        self,
        facility_id: int,
    ) -> list[QRAccessToken]:
        if facility_id <= 0:
            raise ValueError(
                "Facility ID must be greater than zero."
            )

        return await self.repository.get_all_active_by_facility(
            facility_id
        )

    async def deactivate_expired_tokens(self) -> int:
        current_time = self._utc_now()

        expired_tokens = (
            await self.repository.get_expired_active_tokens(
                current_time
            )
        )

        for qr_access_token in expired_tokens:
            await self.repository.deactivate(
                qr_access_token
            )

        if expired_tokens:
            await self.repository.db.flush()
            await self.repository.db.commit()

        return len(expired_tokens)