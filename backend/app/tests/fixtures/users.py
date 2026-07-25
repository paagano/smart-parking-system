"""
Reusable user test data.
"""

from copy import deepcopy


ADMIN_USER = {
    "first_name": "Philip",
    "last_name": "Agano",
    "email": "admin@test.com",
    "phone_number": "0729212981",
    "password": "Password123!",
    "confirm_password": "Password123!",
    "role": "ADMIN",
}


ATTENDANT_USER = {
    "first_name": "John",
    "last_name": "Attendant",
    "email": "attendant@test.com",
    "phone_number": "0729000001",
    "password": "Password123!",
    "confirm_password": "Password123!",
    "role": "ATTENDANT",
}


DRIVER_USER = {
    "first_name": "Jane",
    "last_name": "Driver",
    "email": "driver@test.com",
    "phone_number": "0729000002",
    "password": "Password123!",
    "confirm_password": "Password123!",
    "role": "DRIVER",
}


def admin_user():
    """
    Returns a fresh administrator payload.
    """

    return deepcopy(ADMIN_USER)


def attendant_user():
    """
    Returns a fresh attendant payload.
    """

    return deepcopy(ATTENDANT_USER)


def driver_user():
    """
    Returns a fresh driver payload.
    """

    return deepcopy(DRIVER_USER)