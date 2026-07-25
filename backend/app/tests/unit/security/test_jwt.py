import pytest
from jose import JWTError

from app.core.security import (
    create_access_token,
    decode_token,
)


def test_create_and_decode_token():
    """
    Ensure a JWT can be created and decoded successfully.
    """

    email = "philip.agano@yahoo.com"

    token = create_access_token(
        subject=email,
        user_id=1,
        role="ADMIN",
    )

    assert token is not None
    assert isinstance(token, str)

    payload = decode_token(token)

    assert payload["sub"] == email
    assert payload["uid"] == 1
    assert payload["role"] == "ADMIN"


def test_decode_invalid_token():
    """
    Invalid JWTs should raise JWTError.
    """

    with pytest.raises(JWTError):
        decode_token("this.is.not.a.valid.token")