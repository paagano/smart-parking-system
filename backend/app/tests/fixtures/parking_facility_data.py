"""
Reusable Parking Facility test data.
"""

from copy import deepcopy


PARKING_FACILITY = {
    "name": "Two Rivers Mall",
    "code": "TRM001",
    "facility_type": "SHOPPING_MALL",
    "description": "Shopping mall parking facility.",
    "country": "Kenya",
    "county": "Nairobi",
    "city": "Nairobi",
    "address": "Limuru Road",
    "postal_code": "00100",
    "latitude": -1.210490,
    "longitude": 36.802871,
    "timezone": "Africa/Nairobi",
    "opening_time": "06:00:00",
    "closing_time": "23:00:00",
    "is_active": True,
}


def parking_facility_data():
    """
    Return a fresh parking facility payload.

    A deep copy prevents one test from modifying
    the data used by another test.
    """
    return deepcopy(PARKING_FACILITY)


def duplicate_code_data():
    """
    Returns a facility with the same code
    but a different name.
    """

    facility = deepcopy(PARKING_FACILITY)

    facility["name"] = "Westgate Mall"

    return facility


def duplicate_name_data():
    """
    Returns a facility with the same name
    but a different code.
    """

    facility = deepcopy(PARKING_FACILITY)

    facility["code"] = "WGM001"

    return facility


def updated_facility_data():
    """
    Returns an updated facility payload.
    """

    facility = deepcopy(PARKING_FACILITY)

    facility.update(
        {
            "name": "Two Rivers Mall - Updated",
            "description": "Updated description",
            "city": "Kiambu",
        }
    )

    return facility


def invalid_facility_data():
    """
    Returns intentionally invalid data.
    Used to verify validation errors.
    """

    return {
        "name": "",
        "code": "",
        "facility_type": "INVALID_TYPE",
        "country": "",
        "city": "",
    }