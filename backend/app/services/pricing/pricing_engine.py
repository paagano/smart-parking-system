"""
Pricing Engine

The Pricing Engine is the heart of the Smart Parking pricing
subsystem.

Its responsibility is to orchestrate parking fee calculation
while delegating billing-specific calculations to calculator
strategies.

Responsibilities
----------------
✔ Validate pricing requests
✔ Build pricing context
✔ Calculate parking duration
✔ Select the appropriate calculator
✔ Apply minimum charge
✔ Apply maximum daily charge
✔ Build pricing result

The Pricing Engine intentionally does NOT:

✘ Query the database
✘ Persist data
✘ Update parking sessions
✘ Process payments
✘ Generate receipts
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.services.pricing.calculators import (
    get_calculator,
)
from app.services.pricing.pricing_context import (
    PricingContext,
)
from app.services.pricing.pricing_request import (
    PricingRequest,
)
from app.services.pricing.pricing_result import (
    PricingResult,
)
from app.services.pricing.pricing_utils import (
    calculate_billable_minutes,
    calculate_duration_minutes,
    apply_maximum_daily_charge,
    apply_minimum_charge,
)

from app.services.pricing.pricing_exceptions import (
    InactiveTariffException,
    InvalidParkingDurationException,
    TariffNotEffectiveException,
    TariffNotFoundException,
)


class PricingEngine:
    """
    Enterprise Parking Pricing Engine.

    Coordinates parking fee calculation while delegating
    billing strategy calculations to the appropriate
    calculator implementation.
    """

    # ==========================================================
    # Construction
    # ==========================================================

    def __init__(self) -> None:
        """
        Create a new Pricing Engine.

        The engine is intentionally stateless and therefore
        safe for reuse.
        """

        pass

    # ==========================================================
    # Public API
    # ==========================================================

    def calculate(
        self,
        request: PricingRequest,
    ) -> PricingResult:
        """
        Calculate parking charges.

        Workflow
        --------

        1. Validate request
        2. Build pricing context
        3. Calculate duration
        4. Select calculator
        5. Calculate base amount
        6. Apply minimum charge
        7. Apply daily cap
        8. Build pricing result

        Parameters
        ----------
        request:
            Pricing request.

        Returns
        -------
        PricingResult
        """

        self._validate_request(request)

        context = self._create_context(request)

        context = self._calculate_duration(context)

        context = self._apply_base_calculation(context)

        context = self._apply_minimum_charge(context)

        context = self._apply_maximum_daily_charge(context)

        return self._build_result(context)

    # ==========================================================
    # Context
    # ==========================================================

    def _create_context(
        self,
        request: PricingRequest,
    ) -> PricingContext:
        """
        Build the initial PricingContext.

        The context is progressively enriched during the
        pricing workflow.
        """

        return PricingContext(
            request=request,
            tariff=request.tariff,
            billing_type=request.tariff.billing_type,
            calculated_at=datetime.now(timezone.utc),
        )

    # ==========================================================
    # Validation
    # ==========================================================

    def _validate_request(
        self,
        request: PricingRequest,
    ) -> None:
        """
        Validate the pricing request before calculation.

        Raises
        ------
        InactiveTariffException
            If the supplied tariff is inactive.

        InvalidParkingDurationException
            If the exit time is earlier than the entry time.

        TariffNotEffectiveException
            If the tariff is not valid for the requested
            parking session.
        """

        tariff = request.tariff

        if not tariff.is_active:
            raise InactiveTariffException()

        if request.exit_time < request.entry_time:
            raise InvalidParkingDurationException(
                "Exit time cannot be earlier than entry time."
            )

        if (
            tariff.effective_to is not None
            and request.entry_time > tariff.effective_to
        ):
            raise TariffNotEffectiveException(
                "Tariff is no longer effective."
            )

        if request.entry_time < tariff.effective_from:
            raise TariffNotEffectiveException(
                "Tariff was not yet effective."
            )

    # ==========================================================
    # Duration
    # ==========================================================

    def _calculate_duration(
        self,
        context: PricingContext,
    ) -> PricingContext:
        """
        Calculate parking duration and billable duration.
        """

        duration_minutes = calculate_duration_minutes(
            context.request.entry_time,
            context.request.exit_time,
        )

        billable_minutes = calculate_billable_minutes(
            duration_minutes,
            context.tariff.grace_period_minutes,
        )

        grace_period_applied = (
            billable_minutes < duration_minutes
        )

        return context.model_copy(
            update={
                "duration_minutes": duration_minutes,
                "billable_minutes": billable_minutes,
                "grace_period_applied": grace_period_applied,
            }
        )

    # ==========================================================
    # Base Charge
    # ==========================================================

    def _apply_base_calculation(
        self,
        context: PricingContext,
    ) -> PricingContext:
        """
        Delegate the base charge calculation to the
        appropriate billing strategy.
        """

        calculator = get_calculator(
            context.billing_type
        )

        return calculator.calculate(
            context
        )

    # ==========================================================
    # Minimum Charge
    # ==========================================================

    def _apply_minimum_charge(
        self,
        context: PricingContext,
    ) -> PricingContext:
        """
        Apply the configured minimum charge.

        If no minimum charge exists, the base amount
        is left unchanged.
        """

        minimum_charge = context.tariff.minimum_charge

        if minimum_charge is None:
            return context

        total_amount = apply_minimum_charge(
            base_amount=context.base_amount,
            minimum_charge=minimum_charge,
        )

        return context.model_copy(
            update={
                "total_amount": total_amount,
            }
        )

    # ==========================================================
    # Maximum Daily Charge
    # ==========================================================

    def _apply_maximum_daily_charge(
        self,
        context: PricingContext,
    ) -> PricingContext:
        """
        Apply the configured maximum daily charge.

        If no maximum charge exists, the current total
        amount is retained.
        """

        maximum_daily_charge = (
            context.tariff.max_daily_charge
        )

        if maximum_daily_charge is None:
            return context

        total_amount = apply_maximum_daily_charge(
            amount=context.total_amount,
            maximum_daily_charge=maximum_daily_charge,
        )

        return context.model_copy(
            update={
                "total_amount": total_amount,
            }
        )

    # ==========================================================
    # Result
    # ==========================================================

    def _build_result(
        self,
        context: PricingContext,
    ) -> PricingResult:
        """
        Build the final PricingResult returned to callers.
        """

        total_amount = (
            context.total_amount
            if context.total_amount > Decimal("0.00")
            else context.base_amount
        )

        return PricingResult(
            tariff_id=context.tariff.id,
            tariff_name=context.tariff.name,
            billing_type=context.billing_type,
            duration_minutes=context.duration_minutes,
            billable_minutes=context.billable_minutes,
            grace_period_applied=context.grace_period_applied,
            base_amount=context.base_amount,
            discount_amount=context.discount_amount,
            tax_amount=context.tax_amount,
            total_amount=total_amount,
            calculated_at=context.calculated_at,
        )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(
        self,
    ) -> str:
        """
        String representation.
        """

        return (
            f"{self.__class__.__name__}()"
        )

    