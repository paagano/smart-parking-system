"""
Loyalty Coupon Schemas.

Pydantic schemas for the SmartPark Loyalty Coupon
Programme.

Business rules belong in LoyaltyCouponService.

Persistence belongs in LoyaltyCouponRepository.

The authenticated customer identity is NOT supplied by
customer-facing requests. Customer ownership is resolved
from the authenticated user and loyalty account.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.models.enums import (
    CouponStatus,
    CouponType,
)


# ==========================================================
# Coupon Creation
# ==========================================================


class LoyaltyCouponCreateRequest(BaseModel):
    """
    Request schema for creating a loyalty coupon.

    Customer ownership is resolved by the service layer
    from the authenticated user.

    reward_redemption_id is optional because a coupon may
    either be created independently or be associated with
    a previously redeemed loyalty reward.
    """

    coupon_code: str = Field(
        min_length=1,
        max_length=100,
    )

    coupon_type: CouponType

    value: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
    )

    free_parking_minutes: int | None = Field(
        default=None,
        gt=0,
    )

    status: CouponStatus = CouponStatus.ACTIVE

    is_active: bool = True

    valid_from: datetime | None = None

    valid_until: datetime | None = None

    description: str | None = Field(
        default=None,
        max_length=1000,
    )

    reward_redemption_id: int | None = Field(
        default=None,
        gt=0,
        description=(
            "Optional loyalty reward redemption ID "
            "associated with this coupon."
        ),
    )

    @model_validator(mode="after")
    def validate_coupon_value(
        self,
    ) -> "LoyaltyCouponCreateRequest":
        """
        Validate coupon benefit configuration.

        Discount coupons require a monetary value.

        FREE_PARKING_HOURS requires a positive number of
        parking minutes.

        FREE_PARKING does not require either monetary value
        or parking minutes.
        """

        if self.coupon_type in {
            CouponType.PERCENTAGE_DISCOUNT,
            CouponType.FIXED_AMOUNT_DISCOUNT,
        }:
            if self.value is None:
                raise ValueError(
                    "value is required for discount coupons"
                )

            if self.value <= 0:
                raise ValueError(
                    "value must be greater than zero "
                    "for discount coupons"
                )

        if (
            self.coupon_type
            == CouponType.FREE_PARKING_HOURS
        ):
            if self.free_parking_minutes is None:
                raise ValueError(
                    "free_parking_minutes is required "
                    "for FREE_PARKING_HOURS coupons"
                )

            if self.free_parking_minutes <= 0:
                raise ValueError(
                    "free_parking_minutes must be greater "
                    "than zero"
                )

        return self


# ==========================================================
# Coupon Update
# ==========================================================


class LoyaltyCouponUpdateRequest(BaseModel):
    """
    Request schema for partially updating a loyalty coupon.

    All fields are optional.
    """

    coupon_type: CouponType | None = None

    value: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
    )

    free_parking_minutes: int | None = Field(
        default=None,
        gt=0,
    )

    status: CouponStatus | None = None

    is_active: bool | None = None

    valid_from: datetime | None = None

    valid_until: datetime | None = None

    description: str | None = Field(
        default=None,
        max_length=1000,
    )


# ==========================================================
# Coupon Response
# ==========================================================


class LoyaltyCouponResponse(BaseModel):
    """
    Public representation of a loyalty coupon.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    coupon_code: str

    loyalty_account_id: int

    reward_redemption_id: int | None = None

    coupon_type: CouponType

    value: Decimal | None = None

    free_parking_minutes: int | None = None

    status: CouponStatus

    is_active: bool

    valid_from: datetime

    valid_until: datetime

    used_at: datetime | None = None

    used_payment_transaction_id: int | None = None

    description: str | None = None

    created_at: datetime

    updated_at: datetime


# ==========================================================
# Coupon List Response
# ==========================================================


class LoyaltyCouponListResponse(BaseModel):
    """
    Paginated loyalty coupon response.
    """

    items: list[LoyaltyCouponResponse]

    total: int = Field(
        ge=0,
    )

    limit: int = Field(
        ge=1,
    )

    offset: int = Field(
        ge=0,
    )


# ==========================================================
# Coupon Validation Request
# ==========================================================


class LoyaltyCouponValidationRequest(BaseModel):
    """
    Request schema for validating a coupon.

    The customer submits the coupon code.

    The authenticated customer is resolved by the service
    layer.
    """

    coupon_code: str = Field(
        min_length=1,
        max_length=100,
    )


# ==========================================================
# Coupon Validation Response
# ==========================================================


class LoyaltyCouponValidationResponse(BaseModel):
    """
    Result of validating a loyalty coupon.

    This does not consume or mark the coupon as used.
    """

    coupon: LoyaltyCouponResponse

    valid: bool

    is_active: bool

    not_expired: bool

    customer_owns_coupon: bool

    reason: str | None = None


# ==========================================================
# Coupon Usage Request
# ==========================================================


class LoyaltyCouponUseRequest(BaseModel):
    """
    Request schema for applying a coupon to a payment.

    The payment transaction is supplied by the service/API
    workflow and is not automatically trusted merely because
    the client supplies an ID.
    """

    coupon_code: str = Field(
        min_length=1,
        max_length=100,
    )

    payment_transaction_id: int = Field(
        gt=0,
    )


# ==========================================================
# Coupon Usage Response
# ==========================================================


class LoyaltyCouponUseResponse(BaseModel):
    """
    Response returned after successfully applying a coupon.
    """

    coupon: LoyaltyCouponResponse

    applied: bool

    payment_transaction_id: int

    used_at: datetime

    message: str


# ==========================================================
# Coupon History
# ==========================================================


class LoyaltyCouponHistoryResponse(BaseModel):
    """
    Paginated customer coupon history.
    """

    items: list[LoyaltyCouponResponse]

    total: int = Field(
        ge=0,
    )

    limit: int = Field(
        ge=1,
    )

    offset: int = Field(
        ge=0,
    )


# ==========================================================
# Coupon Status Update
# ==========================================================


class LoyaltyCouponStatusUpdateRequest(BaseModel):
    """
    Request schema for changing the status of a coupon.

    Intended primarily for administrative/service
    operations.
    """

    status: CouponStatus

    is_active: bool | None = None


# ==========================================================
# Coupon Redemption / Application Result
# ==========================================================


class LoyaltyCouponApplicationResult(BaseModel):
    """
    Result returned when a coupon has successfully been
    applied.

    This schema provides both the coupon state and the
    resulting payment linkage.
    """

    coupon: LoyaltyCouponResponse

    payment_transaction_id: int

    applied: bool

    used_at: datetime

    message: str