from enum import Enum

# ==========================================================
# User & Authentication
# ==========================================================

class UserRole(str, Enum):
    DRIVER="DRIVER"
    ATTENDANT="ATTENDANT"
    ADMIN="ADMIN"

    @property
    def label(self):
        return self.value.replace("_"," ").title()

# ==========================================================
# Parking Facilities
# ==========================================================

class FacilityType(str, Enum):
    SHOPPING_MALL="SHOPPING_MALL"
    UNIVERSITY="UNIVERSITY"
    OFFICE="OFFICE"
    AIRPORT="AIRPORT"
    HOSPITAL="HOSPITAL"
    HOTEL="HOTEL"
    RESIDENTIAL="RESIDENTIAL"
    MUNICIPAL="MUNICIPAL"
    STADIUM="STADIUM"
    TRANSPORT_HUB="TRANSPORT_HUB"
    INDUSTRIAL="INDUSTRIAL"
    PUBLIC="PUBLIC"
    OTHER="OTHER"

    @property
    def label(self):
        return self.value.replace("_"," ").title()

# ==========================================================
# Parking Zones
# ==========================================================

class ZoneType(str, Enum):
    BUILDING_LEVEL="BUILDING_LEVEL"
    WING="WING"
    SECTION="SECTION"
    AISLE="AISLE"
    BLOCK="BLOCK"
    REGION="REGION"
    DISTRICT="DISTRICT"
    STREET="STREET"
    TERMINAL="TERMINAL"
    PARKING_LOT="PARKING_LOT"
    CUSTOM="CUSTOM"

    @property
    def label(self):
        return self.value.replace("_"," ").title()

# ==========================================================
# Parking Bays
# ==========================================================

class BayType(str, Enum):
    STANDARD="STANDARD"
    ACCESSIBLE="ACCESSIBLE"
    EV_CHARGING="EV_CHARGING"
    VIP="VIP"
    COMPACT="COMPACT"
    LARGE="LARGE"
    MOTORCYCLE="MOTORCYCLE"
    STAFF="STAFF"
    VISITOR="VISITOR"
    LOADING="LOADING"

    @property
    def label(self):
        return self.value.replace("_"," ").title()

class VehicleType(str, Enum):
    CAR="CAR"
    SUV="SUV"
    TRUCK="TRUCK"
    MOTORCYCLE="MOTORCYCLE"
    BUS="BUS"
    ANY="ANY"

    @property
    def label(self):
        return self.value.replace("_"," ").title()

class BaySize(str, Enum):
    SMALL="SMALL"
    MEDIUM="MEDIUM"
    LARGE="LARGE"

    @property
    def label(self):
        return self.value.replace("_"," ").title()

# ==========================================================
# Parking Sessions
# ==========================================================

class SessionStatus(str, Enum):
    ACTIVE="ACTIVE"
    COMPLETED="COMPLETED"
    CANCELLED="CANCELLED"
    EXPIRED="EXPIRED"

    @property
    def label(self):
        return self.value.replace("_"," ").title()

class EntryMethod(str, Enum):
    MANUAL="MANUAL"
    QR_CODE="QR_CODE"
    RFID="RFID"
    ANPR="ANPR"
    MOBILE_APP="MOBILE_APP"
    SENSOR="SENSOR"

    @property
    def label(self):
        return self.value.replace("_"," ").title()

class ExitMethod(str, Enum):
    MANUAL="MANUAL"
    QR_CODE="QR_CODE"
    RFID="RFID"
    ANPR="ANPR"
    MOBILE_APP="MOBILE_APP"
    SENSOR="SENSOR"

    @property
    def label(self):
        return self.value.replace("_"," ").title()

class SessionSource(str, Enum):
    ATTENDANT="ATTENDANT"
    RESERVATION="RESERVATION"
    DRIVE_IN="DRIVE_IN"
    SENSOR="SENSOR"
    API="API"

    @property
    def label(self):
        return self.value.replace("_"," ").title()

# ==========================================================
# Reservations
# ==========================================================
class ReservationStatus(str, Enum):
    """
    Reservation lifecycle status.
    """

    CREATED = "CREATED"
    CONFIRMED = "CONFIRMED"
    CHECKED_IN = "CHECKED_IN"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()

# ==========================================================
# Payments
# ==========================================================

class PaymentStatus(str, Enum):
    PENDING="PENDING"
    PARTIAL="PARTIAL"
    PAID="PAID"
    FAILED="FAILED"
    WAIVED="WAIVED"
    REFUNDED="REFUNDED"

    @property
    def label(self):
        return self.value.replace("_"," ").title()


# ==========================================================
# Billing Tariffs | Pricing Plans
# ==========================================================

class BillingType(str, Enum):
    """
    Parking tariff billing strategy.
    """

    HOURLY = "HOURLY"
    DAILY = "DAILY"
    FLAT = "FLAT"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()

# ==========================================================
# Sensors
# ==========================================================

class SensorStatus(str, Enum):
    ONLINE="ONLINE"
    OFFLINE="OFFLINE"
    MAINTENANCE="MAINTENANCE"
    FAULTY="FAULTY"

    @property
    def label(self):
        return self.value.replace("_"," ").title()

