from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError

from app.api.dependencies.auth import (
    get_current_active_user,
    oauth2_scheme,
)
from app.api.dependencies.services import get_auth_service
from app.core.security import create_access_token, decode_token
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    RegisterResponse,
    ResetPasswordRequest,
    Token,
)
from app.schemas.user import (
    UserCreate,
    UserResponse,
)
from app.services.auth_service import AuthService


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    user: UserCreate,
    auth_service: Annotated[
        AuthService,
        Depends(get_auth_service),
    ],
):
    """
    Register a new user.
    """

    created_user = await auth_service.register_user(
        user,
    )

    return RegisterResponse(
        message="User registered successfully.",
        user=UserResponse.model_validate(
            created_user,
        ),
    )


@router.post(
    "/login",
    response_model=Token,
)
async def login(
    form_data: Annotated[
        OAuth2PasswordRequestForm,
        Depends(),
    ],
    auth_service: Annotated[
        AuthService,
        Depends(get_auth_service),
    ],
):
    """
    Authenticate a user and return a JWT access token.
    """

    user = await auth_service.authenticate_user(
        email=form_data.username,
        password=form_data.password,
    )

    access_token = create_access_token(
        subject=user.email,
        user_id=user.id,
        role=user.role.value,
        token_version=user.token_version,
    )

    return Token(
        access_token=access_token,
    )


# ==========================================================
# Forgot Password
# ==========================================================

@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK,
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    auth_service: Annotated[
        AuthService,
        Depends(get_auth_service),
    ],
):
    """
    Request a password-reset email.

    The response is intentionally identical whether or not
    the supplied email address belongs to an active account.
    This prevents account enumeration through this endpoint.
    """

    await auth_service.request_password_reset(
        payload.email,
    )

    return {
        "message": (
            "If an account exists for that email address, "
            "a password reset link has been sent."
        ),
    }


@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK,
)
async def reset_password(
    payload: ResetPasswordRequest,
    auth_service: Annotated[
        AuthService,
        Depends(get_auth_service),
    ],
):
    """
    Reset a user's password using a valid password-reset token.
    """

    try:
        await auth_service.reset_password(
            token=payload.token,
            new_password=payload.new_password,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {
        "message": (
            "Your password has been reset successfully. "
            "Please sign in with your new password."
        ),
    }


# ==========================================================
# Email Verification
# ==========================================================

@router.post(
    "/resend-verification",
    status_code=status.HTTP_200_OK,
)
async def resend_verification(
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    auth_service: Annotated[
        AuthService,
        Depends(get_auth_service),
    ],
):
    """
    Resend the email-verification message to the currently
    authenticated user's email address.
    """

    if current_user.is_verified:
        return {
            "message": "Email address is already verified.",
        }

    await auth_service.resend_email_verification(
        current_user,
    )

    return {
        "message": "Email verification message sent successfully.",
    }


@router.post(
    "/verify-email",
    status_code=status.HTTP_200_OK,
)
async def verify_email(
    token: str,
    auth_service: Annotated[
        AuthService,
        Depends(get_auth_service),
    ],
):
    """
    Verify a user's email address using a signed,
    purpose-specific verification token.
    """

    try:
        user = await auth_service.verify_email(
            token,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {
        "message": "Email address verified successfully.",
        "user": UserResponse.model_validate(
            user,
        ),
    }


# ==========================================================
# Logout
# ==========================================================

@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
)
async def logout(
    token: str = Depends(oauth2_scheme),
    auth_service: Annotated[
        AuthService,
        Depends(get_auth_service),
    ] = None,
):
    """
    Logout the currently authenticated session by revoking
    the JWT presented by the client.

    The JWT's unique JTI is stored in the revoked_tokens table
    until the token's original expiration time.
    """

    #
    # Decode the JWT to retrieve its JTI and expiration time.
    #
    try:
        payload = decode_token(
            token,
        )

        token_jti = payload.get(
            "jti",
        )

        token_exp = payload.get(
            "exp",
        )

        if token_jti is None or token_exp is None:
            raise JWTError()

        token_expires_at = datetime.fromtimestamp(
            token_exp,
            tz=timezone.utc,
        )

    except (
        JWTError,
        TypeError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        ) from exc

    #
    # Revoke the JWT.
    #
    await auth_service.logout(
        token_jti=token_jti,
        token_expires_at=token_expires_at,
    )

    return {
        "message": "Logged out successfully.",
    }


# ==========================================================
# Logout All Sessions
# ==========================================================

@router.post(
    "/logout-all",
    status_code=status.HTTP_200_OK,
)
async def logout_all(
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    auth_service: Annotated[
        AuthService,
        Depends(get_auth_service),
    ],
):
    """
    Logout all sessions for the currently authenticated user.

    Incrementing the user's token version invalidates all
    previously issued JWT access tokens for that user.
    """

    await auth_service.logout_all(
        user=current_user,
    )

    return {
        "message": "Logged out from all sessions successfully.",
    }