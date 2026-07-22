import re


def normalize_kenyan_phone(phone_number: str) -> str:
    """
    Normalize Kenyan phone numbers to the format:

        2547XXXXXXXX

    Accepted formats:

        0729212981
        729212981
        254729212981
        +254729212981
        254 729 212 981
        0729 212 981
        0729-212-981

    Returns:
        Normalized phone number.

    Raises:
        ValueError: If the phone number is invalid.
    """

    # Remove spaces, hyphens, brackets and plus sign
    phone = re.sub(r"\D", "", phone_number)

    # Already in international format
    if phone.startswith("254") and len(phone) == 12:
        normalized = phone

    # Local format
    elif phone.startswith("0") and len(phone) == 10:
        normalized = "254" + phone[1:]

    # Missing leading zero
    elif phone.startswith("7") and len(phone) == 9:
        normalized = "254" + phone

    else:
        raise ValueError("Invalid Kenyan phone number.")

    # Final validation
    if (
        len(normalized) != 12
        or not normalized.startswith("2547")
    ):
        raise ValueError("Invalid Kenyan phone number.")

    return normalized