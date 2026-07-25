from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.database.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.user_repository import UserRepository

# =============================================================================
# OAuth2 Scheme
# =============================================================================

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
)


# =============================================================================
# Authentication
# =============================================================================

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Retrieve the currently authenticated user.

    Raises:
        HTTPException:
            If the JWT is invalid or the user does not exist.
    """

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )

    try:
        payload = decode_token(token)

        email = payload.get("sub")

        if email is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    user_repository = UserRepository(db)

    user = await user_repository.get_by_email(email)

    if user is None:
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
) -> User:
    """
    Ensure the authenticated user is active.
    """

    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user.",
        )

    return current_user


# =============================================================================
# Authorization
# =============================================================================

async def require_admin(
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> User:
    """
    Allow access to administrators only.
    """

    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required.",
        )

    return current_user


async def require_attendant(
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> User:
    """
    Allow access to attendants and administrators.
    """

    if current_user.role not in (
        UserRole.ADMIN,
        UserRole.ATTENDANT,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Attendant privileges required.",
        )

    return current_user


async def require_driver(
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> User:
    """
    Any authenticated active user may access driver endpoints.
    """

    return current_user