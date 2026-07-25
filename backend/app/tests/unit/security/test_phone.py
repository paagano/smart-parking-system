import pytest

from app.utils.phone import normalize_kenyan_phone


@pytest.mark.parametrize(
    "input_number, expected",
    [
        ("0729212981", "254729212981"),
        ("729212981", "254729212981"),
        ("254729212981", "254729212981"),
        ("+254729212981", "254729212981"),
        ("254 729 212 981", "254729212981"),
        ("254-729-212-981", "254729212981"),
    ],
)
def test_normalize_phone(input_number, expected):
    """
    Valid Kenyan phone numbers should normalize
    to the international format.
    """

    assert normalize_kenyan_phone(input_number) == expected


@pytest.mark.parametrize(
    "invalid_number",
    [
        "12345",
        "",
        "abcdefgh",
        "111111111111111111",
        "+123456",
    ],
)
def test_invalid_phone(invalid_number):
    """
    Invalid phone numbers should raise ValueError.
    """

    with pytest.raises(ValueError):
        normalize_kenyan_phone(invalid_number)