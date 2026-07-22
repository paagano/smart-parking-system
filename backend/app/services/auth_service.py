from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.exceptions.auth import (
    EmailAlreadyExistsException,
    InvalidCredentialsException,
    PhoneAlreadyExistsException,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate


class AuthService:
    """
    Handles authentication-related business logic.
    """

    def __init__(self):
        self.user_repository = UserRepository()

    def build_user(
        self,
        user_data: UserCreate,
    ) -> User:
        """
        Build a User entity.
        """

        return User(
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            email=user_data.email,
            phone_number=user_data.phone_number,
            password_hash=hash_password(user_data.password),
        )

    def register_user(
        self,
        db: Session,
        user_data: UserCreate,
    ) -> User:
        """
        Register a new user.
        """

        if self.user_repository.get_by_email(
            db,
            user_data.email,
        ):
            raise EmailAlreadyExistsException()

        if self.user_repository.get_by_phone(
            db,
            user_data.phone_number,
        ):
            raise PhoneAlreadyExistsException()

        user = self.build_user(user_data)

        return self.user_repository.create(
            db,
            user,
        )

    def authenticate_user(
        self,
        db: Session,
        email: str,
        password: str,
    ) -> User:
        """
        Authenticate a user.
        """

        user = self.user_repository.get_by_email(
            db,
            email,
        )

        if user is None:
            raise InvalidCredentialsException()

        if not verify_password(
            password,
            user.password_hash,
        ):
            raise InvalidCredentialsException()

        return user