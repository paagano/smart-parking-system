from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status
from jose import JWTError

from app.api.dependencies.auth import (
    get_current_user,
    oauth2_scheme,
)
from app.api.dependencies.services import AuthServiceDep
from app.core.security import decode_token
from app.schemas.user import (
    ChangePasswordRequest,
    UserResponse,
    UserUpdate,
)


router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


# ==========================================================
# Current User
# ==========================================================

@router.get(
    "/me",
    response_model=UserResponse,
)
async def get_me(
    current_user=Depends(get_current_user),
):
    """
    Retrieve the authenticated user.
    """

    return current_user


# ==========================================================
# Update Current User Profile
# ==========================================================

@router.patch(
    "/me",
    response_model=UserResponse,
)
async def update_me(
    user_data: UserUpdate,
    current_user=Depends(get_current_user),
    auth_service: AuthServiceDep = None,
):
    """
    Update the authenticated user's editable profile fields.

    Editable fields:
        - first_name
        - last_name
        - phone_number

    Email, password, role, activation status, and
    verification status cannot be modified through
    this endpoint.
    """

    return await auth_service.update_user_profile(
        user=current_user,
        user_data=user_data,
    )


# ==========================================================
# Upload Current User Profile Picture
# ==========================================================

@router.post(
    "/me/profile-picture",
    response_model=UserResponse,
)
async def upload_profile_picture(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    auth_service: AuthServiceDep = None,
):
    """
    Upload or replace the authenticated user's profile picture.

    The uploaded image is stored using the application's
    configured profile-picture storage service.

    Supported image types and file-size validation are handled
    by the service layer.
    """

    return await auth_service.upload_profile_picture(
        user=current_user,
        file=file,
    )


# ==========================================================
# Delete Current User Profile Picture
# ==========================================================

@router.delete(
    "/me/profile-picture",
    response_model=UserResponse,
)
async def delete_profile_picture(
    current_user=Depends(get_current_user),
    auth_service: AuthServiceDep = None,
):
    """
    Delete the authenticated user's profile picture.

    The profile-picture file is removed from storage and the
    user's profile_picture_url is cleared from the database.

    If the user does not currently have a profile picture,
    the current user profile is returned unchanged.
    """

    return await auth_service.delete_profile_picture(
        user=current_user,
    )


# ==========================================================
# Change Current User Password
# ==========================================================

@router.post(
    "/me/change-password",
)
async def change_password(
    password_data: ChangePasswordRequest,
    current_user=Depends(get_current_user),
    auth_service: AuthServiceDep = None,
    token: str = Depends(oauth2_scheme),
):
    """
    Change the authenticated user's password and revoke
    the JWT used for the password change.

    The current password must be supplied and verified
    before the new password is stored.

    The JWT used for this operation is revoked after the
    password change, requiring the user to authenticate
    again with the new password.
    """

    #
    # Decode the current JWT to retrieve its unique
    # identifier and expiration time.
    #
    try:
        payload = decode_token(token)

        token_jti = payload.get("jti")
        token_exp = payload.get("exp")

        if token_jti is None or token_exp is None:
            raise JWTError()

        token_expires_at = datetime.fromtimestamp(
            token_exp,
            tz=timezone.utc,
        )

    except (JWTError, TypeError, ValueError):
        raise JWTError(
            "Invalid authentication token."
        )

    #
    # Change the password and revoke the JWT used
    # for this operation.
    #
    try:
        await auth_service.change_password(
            user=current_user,
            password_data=password_data,
            token_jti=token_jti,
            token_expires_at=token_expires_at,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {
        "message": "Password changed successfully. "
        "Please log in again.",
    }