from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)

from app.models.enums import UserRole
from app.utils.phone import normalize_kenyan_phone


class UserCreate(BaseModel):
    """
    Schema for registering a new user.
    """

    first_name: str = Field(..., max_length=100)
    last_name: str = Field(..., max_length=100)
    email: EmailStr
    phone_number: str = Field(..., max_length=20)
    password: str = Field(..., min_length=8)

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str) -> str:
        """
        Normalize all Kenyan phone numbers before they
        reach the service layer.
        """
        return normalize_kenyan_phone(value)


class UserUpdate(BaseModel):
    """
    Schema for updating the authenticated user's profile.
    """

    first_name: str | None = Field(
        default=None,
        max_length=100,
    )

    last_name: str | None = Field(
        default=None,
        max_length=100,
    )

    phone_number: str | None = Field(
        default=None,
        max_length=20,
    )

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(
        cls,
        value: str | None,
    ) -> str | None:
        """
        Prevent blank or whitespace-only names while allowing
        omitted fields during a PATCH request.
        """
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("Name cannot be blank.")

        return value

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(
        cls,
        value: str | None,
    ) -> str | None:
        """
        Normalize Kenyan phone numbers before they reach
        the service layer.
        """
        if value is None:
            return None

        return normalize_kenyan_phone(value)


class ChangePasswordRequest(BaseModel):
    """
    Schema for changing the authenticated user's password.

    Password requirements:
        - Minimum 8 characters
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one number
        - At least one special character

    The requirement that the new password must differ from
    the current password is validated in the service layer,
    where the current password is available.
    """

    current_password: str = Field(
        ...,
        min_length=1,
    )

    new_password: str = Field(
        ...,
        min_length=8,
    )

    @field_validator("new_password")
    @classmethod
    def validate_new_password(
        cls,
        value: str,
    ) -> str:
        """
        Validate the new password against the required
        password complexity rules.
        """

        if not any(char.isupper() for char in value):
            raise ValueError(
                "New password must contain at least one uppercase letter."
            )

        if not any(char.islower() for char in value):
            raise ValueError(
                "New password must contain at least one lowercase letter."
            )

        if not any(char.isdigit() for char in value):
            raise ValueError(
                "New password must contain at least one number."
            )

        if not any(not char.isalnum() for char in value):
            raise ValueError(
                "New password must contain at least one special character."
            )

        return value


class UserResponse(BaseModel):
    """
    Public representation of a user.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    email: EmailStr
    phone_number: str
    profile_picture_url: str | None = None
    role: UserRole
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime