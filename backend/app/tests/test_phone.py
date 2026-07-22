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
    assert normalize_kenyan_phone(input_number) == expected


def test_invalid_phone():
    with pytest.raises(ValueError):
        normalize_kenyan_phone("12345")