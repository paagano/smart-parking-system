from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import BaseModel


class RevokedToken(BaseModel):
    """
    Stores JWT identifiers (jti) that have been revoked.

    A revoked JWT remains cryptographically valid but is rejected
    by the authentication dependency when its jti is found here.
    """

    __tablename__ = "revoked_tokens"

    # ==========================================================
    # JWT Identifier
    # ==========================================================

    jti: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    # ==========================================================
    # Token Expiration
    # ==========================================================

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )