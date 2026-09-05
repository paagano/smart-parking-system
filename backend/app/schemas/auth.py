import re

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)


class Token(BaseModel):
    """
    JWT access token returned after successful authentication.
    """

    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """
    Decoded JWT payload.
    """

    sub: EmailStr
    uid: int
    role: str
    exp: int


class RegisterResponse(BaseModel):
    """
    Response returned after successful user registration.
    """

    message: str
    user: "UserResponse"

    model_config = ConfigDict(
        from_attributes=True,
    )


class ForgotPasswordRequest(BaseModel):
    """
    Request payload for initiating a password reset.
    """

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """
    Request payload for completing a password reset.
    """

    token: str = Field(
        ...,
        min_length=1,
    )

    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
    )

    confirm_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
    )

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(
        cls,
        value: str,
    ) -> str:
        """
        Validate password strength.

        Requirements:
        - At least 8 characters
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one number
        - At least one special character
        """

        if len(value) < 8:
            raise ValueError(
                "Password must be at least 8 characters long."
            )

        if not re.search(r"[A-Z]", value):
            raise ValueError(
                "Password must contain at least one uppercase letter."
            )

        if not re.search(r"[a-z]", value):
            raise ValueError(
                "Password must contain at least one lowercase letter."
            )

        if not re.search(r"[0-9]", value):
            raise ValueError(
                "Password must contain at least one number."
            )

        if not re.search(r"[^A-Za-z0-9]", value):
            raise ValueError(
                "Password must contain at least one special character."
            )

        return value

    @model_validator(mode="after")
    def validate_password_confirmation(self):
        """
        Ensure the password confirmation matches
        the new password.
        """

        if self.new_password != self.confirm_password:
            raise ValueError(
                "The new passwords do not match."
            )

        return self


from app.schemas.user import UserResponse


RegisterResponse.model_rebuild()