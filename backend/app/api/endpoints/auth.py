from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.database.dependencies import get_db
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

auth_service = AuthService()


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    user: UserCreate,
    db: Annotated[Session, Depends(get_db)],
):
    """
    Register a new user.
    """

    created_user = auth_service.register_user(
        db=db,
        user_data=user,
    )

    return RegisterResponse(
        message="User registered successfully.",
        user=UserResponse.model_validate(created_user),
    )


@router.post(
    "/login",
    response_model=Token,
)
def login(
    form_data: Annotated[
        OAuth2PasswordRequestForm,
        Depends(),
    ],
    db: Annotated[
        Session,
        Depends(get_db),
    ],
):
    """
    Authenticate a user and return a JWT access token.
    """

    user = auth_service.authenticate_user(
        db=db,
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