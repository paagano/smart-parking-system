from app.core.security import hash_password, verify_password
from app.exceptions.auth import (
    EmailAlreadyExistsException,
    InvalidCredentialsException,
    PhoneAlreadyExistsException,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.services.wallet_service import WalletService


class AuthService:
    """
    Handles authentication-related business logic.
    """

    def __init__(
        self,
        user_repository: UserRepository,
        wallet_service: WalletService,
    ) -> None:
        self.user_repository = user_repository
        self.wallet_service = wallet_service

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
            password_hash=hash_password(
                user_data.password,
            ),
        )

    async def register_user(
        self,
        user_data: UserCreate,
    ) -> User:
        """
        Register a new user and automatically provision
        a wallet for the customer.
        """

        #
        # Ensure email is unique.
        #
        if await self.user_repository.get_by_email(
            user_data.email,
        ):
            raise EmailAlreadyExistsException()

        #
        # Ensure phone number is unique.
        #
        if await self.user_repository.get_by_phone(
            user_data.phone_number,
        ):
            raise PhoneAlreadyExistsException()

        #
        # Build the User entity.
        #
        user = self.build_user(
            user_data,
        )

        #
        # Persist the user.
        #
        await self.user_repository.save(
            user,
        )

        #
        # Commit the user so the database generates
        # the primary key.
        #
        await self.user_repository.commit()

        #
        # Refresh to populate generated fields.
        #
        await self.user_repository.refresh(
            user,
        )

        #
        # Automatically create a wallet for every
        # newly registered customer.
        #
        await self.wallet_service.create_wallet(
            customer_id=user.id,
        )

        return user

    async def authenticate_user(
        self,
        email: str,
        password: str,
    ) -> User:
        """
        Authenticate a user.
        """

        user = await self.user_repository.get_by_email(
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