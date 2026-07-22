from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config.settings import settings

# ==========================================================
# Password Hashing
# ==========================================================

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)


def hash_password(password: str) -> str:
    """
    Hash a plain-text password.

    Args:
        password: Plain-text password.

    Returns:
        Securely hashed password.
    """
    return pwd_context.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    """
    Verify a plain-text password against its hash.

    Args:
        plain_password: Password supplied by the user.
        hashed_password: Password hash stored in the database.

    Returns:
        True if the password is valid, otherwise False.
    """
    return pwd_context.verify(
        plain_password,
        hashed_password,
    )


# ==========================================================
# JWT Token Management
# ==========================================================

def create_access_token(
    *,
    subject: str,
    user_id: int,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create a JWT access token.

    Args:
        subject:
            The unique subject of the token.
            (Normally the user's email.)

        user_id:
            Database ID of the authenticated user.

        role:
            User role (ADMIN, ATTENDANT, DRIVER).

        expires_delta:
            Optional custom token lifetime.

    Returns:
        Encoded JWT access token.
    """

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    payload: dict[str, Any] = {
        "sub": subject,
        "uid": user_id,
        "role": role,
        "exp": expire,
    }

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def decode_token(
    token: str,
) -> dict[str, Any]:
    """
    Decode and validate a JWT token.

    Args:
        token:
            JWT access token.

    Returns:
        Decoded JWT payload.

    Raises:
        JWTError:
            If the token is invalid, malformed,
            expired or has an invalid signature.
    """

    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )