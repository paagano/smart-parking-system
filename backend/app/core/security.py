from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

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
    token_version: int,
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

        token_version:
            User token version. Incrementing this value
            invalidates all previously issued tokens for
            the user.

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

    #
    # Generate a unique identifier for this specific JWT.
    #
    # This allows individual tokens to be revoked without
    # affecting other tokens issued to the same user.
    #
    jti = str(uuid4())

    payload: dict[str, Any] = {
        "sub": subject,
        "uid": user_id,
        "role": role,
        "token_version": token_version,
        "exp": expire,
        "jti": jti,
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


# ==========================================================
# Email Verification Token Management
# ==========================================================

EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS = 24


def create_email_verification_token(
    *,
    user_id: int,
    email: str,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create a short-lived JWT used to verify a user's email
    address.

    This token is intentionally separate from the normal
    access token and contains a dedicated purpose claim so
    that an access token cannot be used as an email
    verification token.

    Args:
        user_id:
            Database ID of the user whose email is being verified.

        email:
            Email address that is being verified.

        expires_delta:
            Optional custom token lifetime.

    Returns:
        Encoded email verification JWT.
    """

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            hours=EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS
        )

    #
    # Generate a unique identifier for this verification token.
    #
    jti = str(uuid4())

    payload: dict[str, Any] = {
        "sub": email,
        "uid": user_id,
        "purpose": "email_verification",
        "exp": expire,
        "jti": jti,
    }

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def decode_email_verification_token(
    token: str,
) -> dict[str, Any]:
    """
    Decode and validate an email verification token.

    The token must contain the dedicated
    ``email_verification`` purpose claim.

    Args:
        token:
            JWT email verification token.

    Returns:
        Decoded verification-token payload.

    Raises:
        JWTError:
            If the token is invalid, malformed, expired,
            incorrectly signed, or is not an email
            verification token.
    """

    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )

    if payload.get("purpose") != "email_verification":
        raise JWTError("Invalid email verification token")

    return payload


# ==========================================================
# Password Reset Token Management
# ==========================================================

PASSWORD_RESET_TOKEN_EXPIRE_HOURS = 1


def create_password_reset_token(
    *,
    user_id: int,
    email: str,
    token_version: int,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create a short-lived JWT used to reset a user's password.

    This token is intentionally separate from the normal
    access token and email verification token. It contains
    a dedicated ``password_reset`` purpose claim.

    The user's current token_version is included so that
    successful password reset can invalidate the reset token
    as well as all previously issued access tokens.

    Args:
        user_id:
            Database ID of the user whose password is being reset.

        email:
            Email address associated with the account.

        token_version:
            Current user token version.

        expires_delta:
            Optional custom token lifetime.

    Returns:
        Encoded password reset JWT.
    """

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            hours=PASSWORD_RESET_TOKEN_EXPIRE_HOURS
        )

    #
    # Generate a unique identifier for this password-reset token.
    #
    jti = str(uuid4())

    payload: dict[str, Any] = {
        "sub": email,
        "uid": user_id,
        "token_version": token_version,
        "purpose": "password_reset",
        "exp": expire,
        "jti": jti,
    }

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def decode_password_reset_token(
    token: str,
) -> dict[str, Any]:
    """
    Decode and validate a password reset token.

    The token must contain the dedicated
    ``password_reset`` purpose claim.

    Args:
        token:
            JWT password reset token.

    Returns:
        Decoded password-reset-token payload.

    Raises:
        JWTError:
            If the token is invalid, malformed, expired,
            incorrectly signed, or is not a password
            reset token.
    """

    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )

    if payload.get("purpose") != "password_reset":
        raise JWTError("Invalid password reset token")

    return payload