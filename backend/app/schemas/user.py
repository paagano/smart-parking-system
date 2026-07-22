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
    role: UserRole
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime