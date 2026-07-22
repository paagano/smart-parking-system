from app.core.security import create_access_token, decode_access_token


def test_create_and_decode_token():
    email = "philip.agano@yahoo.com"

    token = create_access_token(email)

    payload = decode_access_token(token)

    assert payload["sub"] == email