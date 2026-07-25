from enum import Enum


# ==========================================================
# User & Authentication
# ==========================================================

class UserRole(str, Enum):
    """
    Roles assigned to users within the SmartPark AI system.

    Attributes:
        DRIVER:
            Regular user who searches, reserves, and pays for parking.

        ATTENDANT:
            Parking staff responsible for managing parking operations.

        ADMIN:
            System administrator with full access to all system features.
    """

    DRIVER = "DRIVER"
    ATTENDANT = "ATTENDANT"
    ADMIN = "ADMIN"


# ==========================================================
# Parking Facilities
# ==========================================================

class FacilityType(str, Enum):
    """
    Categories of parking facilities supported by the system.
    """

    SHOPPING_MALL = "SHOPPING_MALL"
    UNIVERSITY = "UNIVERSITY"
    OFFICE = "OFFICE"
    AIRPORT = "AIRPORT"
    HOSPITAL = "HOSPITAL"
    HOTEL = "HOTEL"
    RESIDENTIAL = "RESIDENTIAL"
    PUBLIC = "PUBLIC"
    OTHER = "OTHER"


# ==========================================================
# Parking Bays
# ==========================================================

class ParkingBayStatus(str, Enum):
    """
    Current operational status of a parking bay.
    """

    AVAILABLE = "AVAILABLE"
    OCCUPIED = "OCCUPIED"
    RESERVED = "RESERVED"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"


# ==========================================================
# Parking Sessions
# ==========================================================

class ParkingSessionStatus(str, Enum):
    """
    Lifecycle states of a parking session.
    """

    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


# ==========================================================
# Reservations
# ==========================================================

class ReservationStatus(str, Enum):
    """
    Lifecycle states of a parking reservation.
    """

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    COMPLETED = "COMPLETED"


# ==========================================================
# Payments
# ==========================================================

class PaymentStatus(str, Enum):
    """
    Status of a parking payment transaction.
    """

    PENDING = "PENDING"
    SUCCESSFUL = "SUCCESSFUL"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


# ==========================================================
# Sensors
# ==========================================================

class SensorStatus(str, Enum):
    """
    Operational status of a parking sensor.
    """

    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    MAINTENANCE = "MAINTENANCE"
    FAULTY = "FAULTY"