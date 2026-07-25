from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.dependencies.services import get_auth_service
from app.core.security import create_access_token
from app.schemas.auth import (
    RegisterResponse,
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

    created_user = await auth_service.register_user(user)

    return RegisterResponse(
        message="User registered successfully.",
        user=UserResponse.model_validate(created_user),
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
    )

    return Token(
        access_token=access_token,
    )