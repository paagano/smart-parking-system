from app.core.security import (
    hash_password,
    verify_password,
)


def test_password_hashing():
    """
    Passwords should be hashed and verified correctly.
    """

    password = "Password123!"

    hashed_password = hash_password(password)

    assert hashed_password != password

    assert verify_password(
        password,
        hashed_password,
    )

    assert not verify_password(
        "WrongPassword",
        hashed_password,
    )


def test_same_password_produces_different_hashes():
    """
    Bcrypt should generate different hashes
    for the same password because of salting.
    """

    password = "Password123!"

    hash1 = hash_password(password)
    hash2 = hash_password(password)

    assert hash1 != hash2

    assert verify_password(password, hash1)
    assert verify_password(password, hash2)