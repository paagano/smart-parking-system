from enum import Enum


# ==========================================================
# User & Authentication
# ==========================================================

class UserRole(str, Enum):
    DRIVER = "DRIVER"
    ATTENDANT = "ATTENDANT"
    ADMIN = "ADMIN"

    @property
    def label(self):
        return self.value.replace("_", " ").title()


# ==========================================================
# Parking Facilities
# ==========================================================

class FacilityType(str, Enum):
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

    @property
    def label(self):
        return self.value.replace("_", " ").title()


# ==========================================================
# Parking Zones
# ==========================================================

class ZoneType(str, Enum):
    BUILDING_LEVEL = "BUILDING_LEVEL"
    WING = "WING"
    SECTION = "SECTION"
    AISLE = "AISLE"
    BLOCK = "BLOCK"
    REGION = "REGION"
    DISTRICT = "DISTRICT"
    STREET = "STREET"
    TERMINAL = "TERMINAL"
    PARKING_LOT = "PARKING_LOT"
    CUSTOM = "CUSTOM"

    @property
    def label(self):
        return self.value.replace("_", " ").title()


# ==========================================================
# Parking Bays
# ==========================================================

class BayType(str, Enum):
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
    def label(self):
        return self.value.replace("_", " ").title()


class VehicleType(str, Enum):
    CAR = "CAR"
    SUV = "SUV"
    TRUCK = "TRUCK"
    MOTORCYCLE = "MOTORCYCLE"
    BUS = "BUS"
    ANY = "ANY"

    @property
    def label(self):
        return self.value.replace("_", " ").title()


# ==========================================================
# Vehicle Parking Profile
# ==========================================================

class ParkingProfile(str, Enum):
    """
    Vehicle parking profile.

    Used to determine parking preferences,
    eligibility and future smart parking
    recommendations.
    """

    STANDARD = "STANDARD"
    ELECTRIC = "ELECTRIC"
    ACCESSIBLE = "ACCESSIBLE"
    VIP = "VIP"
    COMMERCIAL = "COMMERCIAL"
    EMERGENCY = "EMERGENCY"

    @property
    def label(self):
        return self.value.replace("_", " ").title()


class BaySize(str, Enum):
    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"

    @property
    def label(self):
        return self.value.replace("_", " ").title()


# ==========================================================
# Parking Sessions
# ==========================================================

class SessionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"

    @property
    def label(self):
        return self.value.replace("_", " ").title()


class EntryMethod(str, Enum):
    MANUAL = "MANUAL"
    QR_CODE = "QR_CODE"
    RFID = "RFID"
    ANPR = "ANPR"
    MOBILE_APP = "MOBILE_APP"
    SENSOR = "SENSOR"

    @property
    def label(self):
        return self.value.replace("_", " ").title()


class ExitMethod(str, Enum):
    MANUAL = "MANUAL"
    QR_CODE = "QR_CODE"
    RFID = "RFID"
    ANPR = "ANPR"
    MOBILE_APP = "MOBILE_APP"
    SENSOR = "SENSOR"

    @property
    def label(self):
        return self.value.replace("_", " ").title()


class SessionSource(str, Enum):
    ATTENDANT = "ATTENDANT"
    RESERVATION = "RESERVATION"
    DRIVE_IN = "DRIVE_IN"
    SENSOR = "SENSOR"
    API = "API"

    @property
    def label(self):
        return self.value.replace("_", " ").title()


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
# Reservation Payment Status
# ==========================================================

class ReservationPaymentStatus(str, Enum):
    """
    Payment status of a parking reservation.

    This is intentionally separate from PaymentStatus.
    A reservation only needs to know whether it has
    been paid, partially paid, refunded, or is still
    awaiting payment.
    """

    PENDING = "PENDING"
    PAID = "PAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


# ==========================================================
# Session Payment Status Enum
# ==========================================================

class SessionPaymentStatus(str, Enum):
    """
    Payment status of a parking session.

    Mirrors the existing PostgreSQL enum
    'payment_status'.
    """

    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    FAILED = "FAILED"
    WAIVED = "WAIVED"
    REFUNDED = "REFUNDED"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()


# ==========================================================
# Payments Enums
# ==========================================================

class PaymentMethod(str, Enum):
    """
    Supported payment methods.
    """

    WALLET = "WALLET"
    MPESA = "MPESA"
    AIRTEL_MONEY = "AIRTEL_MONEY"
    CASH = "CASH"
    BANK_CARD = "BANK_CARD"
    BANK_TRANSFER = "BANK_TRANSFER"

    @property
    def label(self):
        return self.value.replace("_", " ").title()


class PaymentStatus(str, Enum):
    """
    Payment transaction lifecycle.
    """

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESSFUL = "SUCCESSFUL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    VOIDED = "VOIDED"

    @property
    def label(self):
        return self.value.replace("_", " ").title()


class PaymentPurpose(str, Enum):
    """
    Business purpose of the payment.
    """

    RESERVATION = "RESERVATION"
    PARKING_SESSION = "PARKING_SESSION"
    WALLET_TOPUP = "WALLET_TOPUP"
    WALLET_REFUND = "WALLET_REFUND"
    PENALTY = "PENALTY"
    SUBSCRIPTION = "SUBSCRIPTION"

    @property
    def label(self):
        return self.value.replace("_", " ").title()


class PaymentProvider(str, Enum):
    """
    Financial service provider.
    """

    INTERNAL = "INTERNAL"
    SAFARICOM = "SAFARICOM"
    AIRTEL = "AIRTEL"
    VISA = "VISA"
    MASTERCARD = "MASTERCARD"
    BANK = "BANK"
    OTHER = "OTHER"


class PaymentType(str, Enum):
    """
    Financial transaction type.
    """

    PAYMENT = "PAYMENT"
    REFUND = "REFUND"
    ADJUSTMENT = "ADJUSTMENT"
    REVERSAL = "REVERSAL"
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"
    LOYALTY_REWARD = "LOYALTY_REWARD"
    LOYALTY_REDEMPTION = "LOYALTY_REDEMPTION"
    WALLET_TOPUP = "WALLET_TOPUP"
    WALLET_DEDUCTION = "WALLET_DEDUCTION"

    @property
    def label(self):
        return self.value.replace("_", " ").title()


class Currency(str, Enum):
    """
    Supported currencies.
    """

    KES = "KES"
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"

    @property
    def label(self):
        return self.value


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
# Receipts
# ==========================================================

class ReceiptType(str, Enum):
    """
    Type of financial receipt/document generated by SmartPark.
    """

    PAYMENT = "PAYMENT"
    REFUND = "REFUND"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()


class ReceiptStatus(str, Enum):
    """
    Lifecycle status of a SmartPark receipt.
    """

    PENDING = "PENDING"
    GENERATED = "GENERATED"
    AVAILABLE = "AVAILABLE"
    FAILED = "FAILED"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()


# ==========================================================
# Sensors | IoT Devices 
# ==========================================================

class SensorStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    MAINTENANCE = "MAINTENANCE"
    FAULTY = "FAULTY"

    @property
    def label(self):
        return self.value.replace("_", " ").title()


# ==========================================================
# Wallet Status
# ==========================================================

class WalletStatus(str, Enum):
    """
    Wallet lifecycle.
    """

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()


# ==========================================================
# Wallet Transaction Type
# ==========================================================

class WalletTransactionType(str, Enum):
    """
    Business meaning of a wallet ledger entry.

    Unlike PaymentType, these values describe how the
    customer's wallet balance changed.
    """

    # ======================================================
    # Funding
    # ======================================================

    TOP_UP = "TOP_UP"
    OPENING_BALANCE = "OPENING_BALANCE"
    CREDIT = "CREDIT"

    # ======================================================
    # Spending
    # ======================================================

    DEBIT = "DEBIT"
    PAYMENT = "PAYMENT"

    # ======================================================
    # Reservations / Holds
    # ======================================================

    RESERVATION_HOLD = "RESERVATION_HOLD"
    RESERVATION_RELEASE = "RESERVATION_RELEASE"

    # ======================================================
    # Refunds / Reversals
    # ======================================================

    REFUND = "REFUND"
    REVERSAL = "REVERSAL"

    # ======================================================
    # Administration
    # ======================================================

    ADJUSTMENT = "ADJUSTMENT"
    SYSTEM_CORRECTION = "SYSTEM_CORRECTION"

    # ======================================================
    # Loyalty
    # ======================================================

    LOYALTY_REWARD = "LOYALTY_REWARD"
    LOYALTY_REDEMPTION = "LOYALTY_REDEMPTION"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()


# ==========================================================
# Wallet Transaction Status
# ==========================================================

class WalletTransactionStatus(str, Enum):
    """
    Wallet transaction lifecycle.
    """

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REVERSED = "REVERSED"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()


# ==========================================================
# Notifications
# ==========================================================

class NotificationType(str, Enum):
    """
    Business event that triggered the notification.
    """

    RESERVATION_CREATED = "RESERVATION_CREATED"
    RESERVATION_CONFIRMED = "RESERVATION_CONFIRMED"
    RESERVATION_CANCELLED = "RESERVATION_CANCELLED"
    RESERVATION_EXPIRED = "RESERVATION_EXPIRED"

    SESSION_CHECKED_IN = "SESSION_CHECKED_IN"
    SESSION_CHECKED_OUT = "SESSION_CHECKED_OUT"

    PAYMENT_INITIATED = "PAYMENT_INITIATED"
    PAYMENT_SUCCESSFUL = "PAYMENT_SUCCESSFUL"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    PAYMENT_REFUNDED = "PAYMENT_REFUNDED"

    RECEIPT_AVAILABLE = "RECEIPT_AVAILABLE"

    LOYALTY_REWARD = "LOYALTY_REWARD"

    SYSTEM = "SYSTEM"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()


class NotificationChannel(str, Enum):
    """
    Delivery channel through which a notification is sent.
    """

    IN_APP = "IN_APP"
    SMS = "SMS"
    EMAIL = "EMAIL"
    PUSH = "PUSH"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()


class NotificationStatus(str, Enum):
    """
    Delivery lifecycle of a notification.
    """

    PENDING = "PENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()


class NotificationPriority(str, Enum):
    """
    Priority assigned to a notification.
    """

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()

# ==========================================================
# Loyalty
# ==========================================================

class LoyaltyTier(str, Enum):
    """
    Loyalty membership tier.

    The tier thresholds and benefits are defined separately
    from the enum.
    """

    BRONZE = "BRONZE"
    SILVER = "SILVER"
    GOLD = "GOLD"
    PLATINUM = "PLATINUM"

class LoyaltyPointTransactionType(str, Enum):
    """
    Type of loyalty point ledger transaction.
    """

    EARN = "EARN"
    REDEEM = "REDEEM"
    REFERRAL_BONUS = "REFERRAL_BONUS"
    ADJUSTMENT = "ADJUSTMENT"
    REVERSAL = "REVERSAL"
    EXPIRATION = "EXPIRATION"

class LoyaltyRewardType(str, Enum):
    """
    Type of loyalty reward.
    """

    DISCOUNT = "DISCOUNT"
    FREE_PARKING = "FREE_PARKING"
    COUPON = "COUPON"

class ReferralStatus(str, Enum):
    """
    Lifecycle status of a customer referral.
    """

    PENDING = "PENDING"
    QUALIFIED = "QUALIFIED"
    REWARDED = "REWARDED"
    CANCELLED = "CANCELLED"

class RewardRedemptionStatus(str, Enum):
    """
    Lifecycle status of a loyalty reward redemption.
    """

    PENDING = "PENDING"
    REDEEMED = "REDEEMED"
    CANCELLED = "CANCELLED"