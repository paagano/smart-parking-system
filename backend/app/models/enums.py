from enum import Enum


class UserRole(str, Enum):
    """
    User roles within the SmartPark AI system.
    """

    DRIVER = "DRIVER"
    ATTENDANT = "ATTENDANT"
    ADMIN = "ADMIN"