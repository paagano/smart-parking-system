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
    MUNICIPAL = "MUNICIPAL"
    STADIUM = "STADIUM"
    TRANSPORT_HUB = "TRANSPORT_HUB"
    INDUSTRIAL = "INDUSTRIAL"
    PUBLIC = "PUBLIC"
    OTHER = "OTHER"


# ==========================================================
# Parking Zones
# ==========================================================

class ZoneType(str, Enum):
    """
    Classification of parking zones within a parking facility.

    Parking Zones provide a flexible hierarchical structure that allows
    SmartPark AI to model a wide variety of parking environments,
    including shopping malls, office complexes, airports, universities,
    hospitals, residential estates, and open municipal parking.

    Examples:
        Shopping Mall
            Basement B1 (BUILDING_LEVEL)
                └── Aisle A (AISLE)

        Nairobi City
            CBD (DISTRICT)
                └── Moi Avenue (STREET)

        Airport
            Terminal 1A (TERMINAL)
                └── Long Stay (PARKING_LOT)
    """

    # Building Structures
    BUILDING_LEVEL = "BUILDING_LEVEL"
    WING = "WING"
    SECTION = "SECTION"
    AISLE = "AISLE"
    BLOCK = "BLOCK"

    # Geographic Structures
    REGION = "REGION"
    DISTRICT = "DISTRICT"
    STREET = "STREET"

    # Transport & Public Infrastructure
    TERMINAL = "TERMINAL"
    PARKING_LOT = "PARKING_LOT"

    # Generic
    CUSTOM = "CUSTOM"

    @property
    def label(self) -> str:
        """
        Return a human-readable version of the zone type.

        Example:
            BUILDING_LEVEL -> Building Level
        """
        return self.value.replace("_", " ").title()


# ==========================================================
# Parking Bays
# ==========================================================

class BayType(str, Enum):
    """
    Classification of parking bays.

    Defines the purpose or characteristics of a parking bay.
    """

    STANDARD = "STANDARD"
    ACCESSIBLE = "ACCESSIBLE"
    EV_CHARGING = "EV_CHARGING"
    VIP = "VIP"
    COMPACT = "COMPACT"
    LARGE = "LARGE"
    MOTORCYCLE = "MOTORCYCLE"
    STAFF = "STAFF"
    VISITOR = "VISITOR"
    LOADING = "LOADING"

    @property
    def label(self) -> str:
        """
        Human-readable version of the bay type.
        """
        return self.value.replace("_", " ").title()


class VehicleType(str, Enum):
    """
    Vehicle categories permitted to use a parking bay.
    """

    CAR = "CAR"
    SUV = "SUV"
    TRUCK = "TRUCK"
    MOTORCYCLE = "MOTORCYCLE"
    BUS = "BUS"
    ANY = "ANY"

    @property
    def label(self) -> str:
        """
        Human-readable version of the vehicle type.
        """
        return self.value.replace("_", " ").title()


class BaySize(str, Enum):
    """
    Physical size classification of a parking bay.
    """

    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"

    @property
    def label(self) -> str:
        """
        Human-readable version of the bay size.
        """
        return self.value.replace("_", " ").title()


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