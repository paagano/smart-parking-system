from pydantic import BaseModel, ConfigDict, EmailStr


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


from app.schemas.user import UserResponse

RegisterResponse.model_rebuild()