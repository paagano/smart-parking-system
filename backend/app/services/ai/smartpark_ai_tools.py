"""
SmartPark AI Tools

SmartPark data and reservation tools exposed to the SmartPark AI assistant.

These tools provide GPT with trusted SmartPark data from the
application database. Reservation creation is delegated to the
existing ParkingReservationService so the application
continues to enforce its existing validation, pricing,
conflict detection, transaction, and notification rules.

Current tools:
    - get_facilities
    - get_facility_details
    - get_facility_bays
    - get_facility_availability
    - get_nearest_facilities
    - get_customer_vehicles
    - get_my_vehicles
    - add_vehicle
    - set_default_vehicle
    - deactivate_vehicle
    - activate_vehicle
    - edit_vehicle
    - delete_vehicle
    - get_user_reservations
    - get_user_active_session
    - get_user_active_sessions
    - find_available_parking
    - navigate_to_facility
    - find_available_reservation_bay
    - get_30_minute_occupancy_forecast
    - create_reservation
    - verify_receipt
    - get_my_loyalty_program
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    ParkingProfile,
    ReservationStatus,
    SessionStatus,
    VehicleType,
)
from app.models.parking_bay import ParkingBay
from app.models.parking_facility import ParkingFacility
from app.models.parking_session import ParkingSession
from app.models.parking_reservation import ParkingReservation
from app.models.vehicle import Vehicle
from app.models.parking_zone import ParkingZone

from app.repositories.vehicle_repository import VehicleRepository

from app.schemas.parking_reservation import ParkingReservationCreate
from app.schemas.vehicle import VehicleUpdate

from app.services.parking_reservation_service import ParkingReservationService
from app.services.receipt_service import ReceiptService
from app.services.loyalty_service import LoyaltyService
from app.services.loyalty_reward_service import LoyaltyRewardService
from app.services.vehicle_service import VehicleService
from app.exceptions.handlers import NotFoundException
from app.ml.production.service import ProductionForecastService


SMARTPARK_TIMEZONE = ZoneInfo("Africa/Nairobi")


class SmartParkAITools:
    """
    SmartPark data and reservation tools used by the AI assistant.
    """

    def __init__(
        self,
        db: AsyncSession,
        reservation_service: ParkingReservationService | None = None,
        vehicle_repository: VehicleRepository | None = None,
        vehicle_service: VehicleService | None = None,
        forecast_service: ProductionForecastService | None = None,
        receipt_service: ReceiptService | None = None,
        loyalty_service: LoyaltyService | None = None,
        loyalty_reward_service: LoyaltyRewardService | None = None,
    ) -> None:
        """
        Create the SmartPark AI tools service.

        Args:
            db:
                Active asynchronous SQLAlchemy database session.
        """

        self.db = db
        self.reservation_service = reservation_service
        self.vehicle_repository = vehicle_repository
        self.vehicle_service = vehicle_service
        self.forecast_service = forecast_service
        self.receipt_service = receipt_service
        self.loyalty_service = loyalty_service
        self.loyalty_reward_service = loyalty_reward_service

    # ==========================================================
    # Facilities
    # ==========================================================

    async def get_facilities(
        self,
        *,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Return SmartPark parking facilities.

        By default, only active facilities are returned.

        This tool is useful for questions such as:

            "What parking facilities are available?"
            "Show me the SmartPark parking locations."
            "Which parking facilities do you have?"
        """

        query = (
            select(ParkingFacility)
            .order_by(ParkingFacility.name)
        )

        if active_only:
            query = query.where(
                ParkingFacility.is_active.is_(True)
            )

        result = await self.db.execute(query)

        facilities = result.scalars().all()

        return [
            self._facility_to_dict(facility)
            for facility in facilities
        ]

    # ==========================================================
    # Nearest Facilities
    # ==========================================================

    async def get_nearest_facilities(
        self,
        latitude: float,
        longitude: float,
        *,
        limit: int = 5,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Return the nearest SmartPark parking facilities to a
        supplied geographic coordinate.

        Distance is calculated using the Haversine formula.

        Args:
            latitude:
                User/current latitude in decimal degrees.

            longitude:
                User/current longitude in decimal degrees.

            limit:
                Maximum number of facilities to return.
                Defaults to 5.

            active_only:
                Whether to return only active facilities.
                Defaults to True.

        Returns:
            A list of nearby facilities ordered from nearest
            to farthest.

        Important:
            Facilities without valid latitude/longitude values
            are excluded because their distance cannot be
            calculated.
        """

        # ------------------------------------------------------
        # Validate coordinates
        # ------------------------------------------------------

        if not -90 <= latitude <= 90:
            raise ValueError(
                "Latitude must be between -90 and 90."
            )

        if not -180 <= longitude <= 180:
            raise ValueError(
                "Longitude must be between -180 and 180."
            )

        # Keep the result size sensible.
        limit = max(
            1,
            min(limit, 20),
        )

        # ------------------------------------------------------
        # Retrieve facilities that have geographic coordinates.
        # ------------------------------------------------------

        query = (
            select(ParkingFacility)
            .where(
                ParkingFacility.latitude.is_not(None),
                ParkingFacility.longitude.is_not(None),
            )
            .order_by(ParkingFacility.name)
        )

        if active_only:
            query = query.where(
                ParkingFacility.is_active.is_(True)
            )

        result = await self.db.execute(query)

        facilities = result.scalars().all()

        # ------------------------------------------------------
        # Calculate distance for every facility.
        # ------------------------------------------------------

        nearby_facilities: list[
            tuple[float, ParkingFacility]
        ] = []

        for facility in facilities:
            if (
                facility.latitude is None
                or facility.longitude is None
            ):
                continue

            distance_km = self._calculate_distance_km(
                latitude,
                longitude,
                facility.latitude,
                facility.longitude,
            )

            nearby_facilities.append(
                (
                    distance_km,
                    facility,
                )
            )

        # ------------------------------------------------------
        # Sort nearest → farthest.
        # ------------------------------------------------------

        nearby_facilities.sort(
            key=lambda item: (
                item[0],
                item[1].name.lower(),
            )
        )

        # ------------------------------------------------------
        # Return requested number of facilities.
        # ------------------------------------------------------

        results: list[dict[str, Any]] = []

        for distance_km, facility in nearby_facilities[:limit]:
            facility_data = self._facility_to_dict(
                facility
            )

            facility_data["distance_km"] = round(
                distance_km,
                2,
            )

            facility_data["distance_meters"] = round(
                distance_km * 1000,
            )

            results.append(
                facility_data
            )

        return results

    # ==========================================================
    # Facility Details
    # ==========================================================

    async def get_facility_details(
        self,
        facility_id: int | None = None,
        facility_name: str | None = None,
        facility_code: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Return details for one parking facility.

        The facility can be identified by:

            - facility_id
            - facility_name
            - facility_code

        Name matching is intentionally tolerant of differences
        in capitalization, whitespace, punctuation, and partial
        facility names.

        At least one identifier should be supplied.

        Returns:
            A dictionary containing facility information,
            or None when no matching facility exists.
        """

        facility: ParkingFacility | None = None

        # ------------------------------------------------------
        # Search by ID
        # ------------------------------------------------------

        if facility_id is not None:
            result = await self.db.execute(
                select(ParkingFacility).where(
                    ParkingFacility.id == facility_id
                )
            )

            facility = result.scalar_one_or_none()

        # ------------------------------------------------------
        # Search by code
        # ------------------------------------------------------

        elif facility_code:
            normalized_code = (
                facility_code
                .strip()
                .upper()
            )

            result = await self.db.execute(
                select(ParkingFacility).where(
                    func.upper(
                        func.trim(
                            ParkingFacility.code
                        )
                    )
                    == normalized_code
                )
            )

            facility = result.scalar_one_or_none()

        # ------------------------------------------------------
        # Search by name
        # ------------------------------------------------------

        elif facility_name:
            requested_name = (
                self._normalize_search_text(
                    facility_name
                )
            )

            if requested_name:
                # --------------------------------------------------
                # First attempt: database substring search.
                # --------------------------------------------------

                search = (
                    f"%{facility_name.strip()}%"
                )

                result = await self.db.execute(
                    select(ParkingFacility)
                    .where(
                        ParkingFacility.name.ilike(
                            search
                        )
                    )
                    .order_by(
                        ParkingFacility.name
                    )
                )

                candidates = list(
                    result.scalars().all()
                )

                # --------------------------------------------------
                # Second attempt: normalized Python matching.
                # --------------------------------------------------

                if not candidates:
                    result = await self.db.execute(
                        select(ParkingFacility)
                        .order_by(
                            ParkingFacility.name
                        )
                    )

                    all_facilities = list(
                        result.scalars().all()
                    )

                    # ------------------------------------------------
                    # Exact normalized match
                    # ------------------------------------------------

                    exact_matches = [
                        item
                        for item in all_facilities
                        if (
                            self._normalize_search_text(
                                item.name
                            )
                            == requested_name
                        )
                    ]

                    if exact_matches:
                        candidates = exact_matches

                    else:
                        # --------------------------------------------
                        # Normalized partial match
                        # --------------------------------------------

                        partial_matches = [
                            item
                            for item in all_facilities
                            if (
                                requested_name
                                in self._normalize_search_text(
                                    item.name
                                )
                            )
                            or (
                                self._normalize_search_text(
                                    item.name
                                )
                                in requested_name
                            )
                        ]

                        if partial_matches:
                            candidates = partial_matches

                        else:
                            # ----------------------------------------
                            # Token-based fallback.
                            #
                            # Example:
                            # "Two Rivers" can match
                            # "Two Rivers Mall Parking".
                            # ----------------------------------------

                            requested_tokens = set(
                                requested_name.split()
                            )

                            token_matches: list[
                                tuple[int, ParkingFacility]
                            ] = []

                            for item in all_facilities:
                                candidate_name = (
                                    self._normalize_search_text(
                                        item.name
                                    )
                                )

                                candidate_tokens = set(
                                    candidate_name.split()
                                )

                                overlap = len(
                                    requested_tokens
                                    & candidate_tokens
                                )

                                if overlap > 0:
                                    token_matches.append(
                                        (
                                            overlap,
                                            item,
                                        )
                                    )

                            if token_matches:
                                token_matches.sort(
                                    key=lambda item: (
                                        -item[0],
                                        item[1].name.lower(),
                                    )
                                )

                                best_overlap = (
                                    token_matches[0][0]
                                )

                                candidates = [
                                    item
                                    for overlap, item
                                    in token_matches
                                    if overlap
                                    == best_overlap
                                ]

                # --------------------------------------------------
                # Select the best candidate.
                # --------------------------------------------------

                if candidates:
                    exact_candidates = [
                        item
                        for item in candidates
                        if (
                            self._normalize_search_text(
                                item.name
                            )
                            == requested_name
                        )
                    ]

                    if exact_candidates:
                        facility = (
                            exact_candidates[0]
                        )
                    else:
                        facility = candidates[0]

        if facility is None:
            return None

        return self._facility_to_dict(
            facility
        )

    # ==========================================================
    # Facility Bays
    # ==========================================================

    async def get_facility_bays(
        self,
        facility_id: int,
        *,
        active_only: bool = True,
        ev_only: bool = False,
        accessible_only: bool = False,
        vip_only: bool = False,
        reservable_only: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Return parking bays belonging to a facility.

        Parking bays belong to zones, and zones belong to facilities.

        Optional filters allow the AI to answer questions such as:

            "Show me the bays at Two Rivers."
            "Does this facility have EV charging bays?"
            "Show me accessible bays."
            "Are there VIP bays?"
            "Which bays can be reserved?"
        """

        query = (
            select(ParkingBay)
            .join(
                ParkingZone,
                ParkingZone.id
                == ParkingBay.zone_id,
            )
            .where(
                ParkingZone.facility_id
                == facility_id
            )
        )

        if active_only:
            query = query.where(
                ParkingBay.is_active.is_(True)
            )

            query = query.where(
                ParkingZone.is_active.is_(True)
            )

        if ev_only:
            query = query.where(
                ParkingBay.is_ev_charging.is_(True)
            )

        if accessible_only:
            query = query.where(
                ParkingBay.is_accessible.is_(True)
            )

        if vip_only:
            query = query.where(
                ParkingBay.is_vip.is_(True)
            )

        if reservable_only:
            query = query.where(
                ParkingBay.is_reservable.is_(True)
            )

        query = query.order_by(
            ParkingBay.sort_order,
            ParkingBay.bay_number,
        )

        result = await self.db.execute(
            query
        )

        bays = result.scalars().all()

        return [
            self._bay_to_dict(bay)
            for bay in bays
        ]

    # ==========================================================
    # Facility Availability
    # ==========================================================

    async def get_facility_availability(
        self,
        facility_id: int,
    ) -> dict[str, Any]:
        """
        Calculate the current parking availability for a facility.

        Availability is derived from:

            Active parking bays
                    minus
            Bays with ACTIVE parking sessions

        This intentionally does not rely on an is_occupied column
        because ParkingBay currently does not contain one.

        Returns:
            A summary containing:

                - total_active_bays
                - occupied_bays
                - available_bays
                - occupancy_percentage
                - available_percentage
        """

        # ------------------------------------------------------
        # Verify facility
        # ------------------------------------------------------

        facility_result = await self.db.execute(
            select(ParkingFacility).where(
                ParkingFacility.id
                == facility_id
            )
        )

        facility = (
            facility_result.scalar_one_or_none()
        )

        if facility is None:
            return {
                "facility_id": facility_id,
                "facility_found": False,
                "facility_name": None,
                "total_active_bays": 0,
                "occupied_bays": 0,
                "available_bays": 0,
                "occupancy_percentage": 0.0,
                "available_percentage": 0.0,
            }

        # ------------------------------------------------------
        # Count active bays
        # ------------------------------------------------------

        total_active_bays_result = await self.db.execute(
            select(
                func.count(
                    ParkingBay.id
                )
            )
            .join(
                ParkingZone,
                ParkingZone.id
                == ParkingBay.zone_id,
            )
            .where(
                ParkingZone.facility_id
                == facility_id,
                ParkingZone.is_active.is_(True),
                ParkingBay.is_active.is_(True),
            )
        )

        total_active_bays = (
            total_active_bays_result.scalar_one()
            or 0
        )

        # ------------------------------------------------------
        # Count occupied active bays
        #
        # A bay is considered occupied when it has an ACTIVE
        # ParkingSession.
        # ------------------------------------------------------

        occupied_bays_result = await self.db.execute(
            select(
                func.count(
                    func.distinct(
                        ParkingSession.parking_bay_id
                    )
                )
            )
            .join(
                ParkingBay,
                ParkingBay.id
                == ParkingSession.parking_bay_id,
            )
            .join(
                ParkingZone,
                ParkingZone.id
                == ParkingBay.zone_id,
            )
            .where(
                ParkingZone.facility_id
                == facility_id,
                ParkingZone.is_active.is_(True),
                ParkingBay.is_active.is_(True),
                ParkingSession.status
                == SessionStatus.ACTIVE,
            )
        )

        occupied_bays = (
            occupied_bays_result.scalar_one()
            or 0
        )

        # ------------------------------------------------------
        # Calculate availability
        # ------------------------------------------------------

        available_bays = max(
            total_active_bays
            - occupied_bays,
            0,
        )

        if total_active_bays > 0:
            occupancy_percentage = round(
                (
                    occupied_bays
                    / total_active_bays
                )
                * 100,
                2,
            )

            available_percentage = round(
                (
                    available_bays
                    / total_active_bays
                )
                * 100,
                2,
            )

        else:
            occupancy_percentage = 0.0
            available_percentage = 0.0

        return {
            "facility_id": facility.id,
            "facility_found": True,
            "facility_name": facility.name,
            "facility_code": facility.code,
            "total_active_bays": total_active_bays,
            "occupied_bays": occupied_bays,
            "available_bays": available_bays,
            "occupancy_percentage": occupancy_percentage,
            "available_percentage": available_percentage,
        }

    # ==========================================================
    # 30-Minute Occupancy Forecast
    # ==========================================================

    async def get_30_minute_occupancy_forecast(
        self,
        *,
        facility_id: int,
        prediction_timestamp: datetime,
        lookback_minutes: int = 1440,
    ) -> dict[str, Any]:
        """
        Generate the production 30-minute parking occupancy forecast
        for a SmartPark facility.

        This delegates inference to the existing production forecasting
        service and returns the validated production result together
        with the real facility identity.
        """

        if self.forecast_service is None:
            raise RuntimeError(
                "Production forecast service is not configured for SmartPark AI."
            )

        facility_result = await self.db.execute(
            select(ParkingFacility).where(
                ParkingFacility.id == facility_id,
                ParkingFacility.is_active.is_(True),
            )
        )

        facility = facility_result.scalar_one_or_none()

        if facility is None:
            return {
                "facility_id": facility_id,
                "facility_found": False,
                "message": (
                    "The requested parking facility was not found "
                    "or is inactive."
                ),
            }

        try:
            result = await self.forecast_service.forecast(
                facility_id=facility_id,
                prediction_timestamp=prediction_timestamp,
                lookback_minutes=lookback_minutes,
            )
        except Exception as exc:
            # Diagnostic-only change: preserve the existing forecast flow,
            # but expose the actual production-service exception so the
            # caller can report the real reason instead of a generic
            # "operation could not be completed" message.
            return {
                "facility_id": facility_id,
                "facility_name": facility.name,
                "facility_code": facility.code,
                "facility_timezone": facility.timezone,
                "forecast_generated": False,
                "prediction_timestamp": prediction_timestamp.isoformat(),
                "forecast_horizon_minutes": 30,
                "error_type": type(exc).__name__,
                "error": str(exc) or repr(exc),
            }

        forecast = result.to_dict()

        forecast.update(
            {
                "facility_name": facility.name,
                "facility_code": facility.code,
                "facility_timezone": facility.timezone,
            }
        )

        return forecast

    # ==========================================================
    # Customer Vehicles
    # ==========================================================

    async def get_customer_vehicles(
        self,
        *,
        customer_id: int,
    ) -> list[dict[str, Any]]:
        """
        Return the authenticated customer's active registered vehicles.

        The customer ID is supplied by the authenticated backend request
        and is never accepted from the AI model.
        """

        if self.vehicle_repository is None:
            raise RuntimeError(
                "Vehicle repository is not configured for SmartPark AI."
            )

        vehicles = await self.vehicle_repository.get_active_by_customer_id(
            customer_id,
        )

        # Present the customer's default vehicle first so the AI can
        # clearly identify it while still allowing the customer to choose
        # any registered vehicle or a borrowed/unregistered vehicle.
        vehicles = sorted(
            vehicles,
            key=lambda vehicle: (
                not bool(vehicle.is_default),
                (
                    vehicle.registration_number or ""
                ).strip().upper(),
                vehicle.id,
            ),
        )

        results: list[dict[str, Any]] = []

        for selection_number, vehicle in enumerate(vehicles, start=1):
            vehicle_data = self._vehicle_to_dict(vehicle)
            vehicle_data["selection_number"] = selection_number
            results.append(vehicle_data)

        return results

    # ==========================================================
    # Customer Vehicle Management
    # ==========================================================

    async def get_my_vehicles(
        self,
        *,
        customer_id: int,
    ) -> list[dict[str, Any]]:
        """
        Return all vehicles belonging to the authenticated customer,
        including inactive vehicles.

        This management view is intentionally separate from
        get_customer_vehicles(), which returns active vehicles for
        reservation vehicle selection.
        """

        if self.vehicle_service is None:
            raise RuntimeError(
                "Vehicle service is not configured for SmartPark AI."
            )

        vehicles = await self.vehicle_service.get_customer_vehicles(
            customer_id=customer_id,
        )

        vehicles = sorted(
            vehicles,
            key=lambda vehicle: (
                not bool(vehicle.is_active),
                not bool(vehicle.is_default),
                (vehicle.registration_number or "").strip().upper(),
                vehicle.id,
            ),
        )

        results: list[dict[str, Any]] = []

        for vehicle in vehicles:
            # Do not add a presentation/selection number here.
            # Vehicle management lists must be numbered by the AI from 1..N
            # in the exact order returned, while the real vehicle ID remains
            # available internally for trusted management operations.
            results.append(self._vehicle_to_dict(vehicle))

        return results

    async def add_vehicle(
        self,
        *,
        customer_id: int,
        plate_country: str = "KE",
        registration_number: str,
        make: str,
        model: str,
        vehicle_type: str,
        parking_profile: str = "STANDARD",
        nickname: str | None = None,
        colour: str | None = None,
        year: int | None = None,
        is_default: bool = False,
    ) -> dict[str, Any]:
        """
        Add a new registered vehicle for the authenticated customer.

        Vehicle ownership and all validation are delegated to the
        existing VehicleService.
        """

        if self.vehicle_service is None:
            raise RuntimeError(
                "Vehicle service is not configured for SmartPark AI."
            )

        from app.schemas.vehicle import VehicleCreate

        data = VehicleCreate(
            plate_country=plate_country.strip().upper(),
            registration_number=registration_number.strip(),
            nickname=nickname.strip() if nickname else None,
            make=make.strip(),
            model=model.strip(),
            colour=colour.strip() if colour else None,
            year=year,
            vehicle_type=VehicleType(str(vehicle_type).upper()),
            parking_profile=ParkingProfile(str(parking_profile).upper()),
            is_default=bool(is_default),
        )

        vehicle = await self.vehicle_service.create_vehicle(
            customer_id=customer_id,
            data=data,
        )

        return self._vehicle_to_dict(vehicle)

    async def set_default_vehicle(
        self,
        *,
        customer_id: int,
        vehicle_id: int,
    ) -> dict[str, Any]:
        """
        Set one of the authenticated customer's active vehicles as default.
        """

        if self.vehicle_service is None:
            raise RuntimeError(
                "Vehicle service is not configured for SmartPark AI."
            )

        vehicle = await self.vehicle_service.set_default_vehicle(
            vehicle_id=vehicle_id,
            customer_id=customer_id,
        )

        return self._vehicle_to_dict(vehicle)

    async def activate_vehicle(
        self,
        *,
        customer_id: int,
        vehicle_id: int,
    ) -> dict[str, Any]:
        """
        Reactivate one of the authenticated customer's inactive vehicles.
        """

        if self.vehicle_service is None:
            raise RuntimeError(
                "Vehicle service is not configured for SmartPark AI."
            )

        vehicle = await self.vehicle_service.activate_vehicle(
            vehicle_id=vehicle_id,
            customer_id=customer_id,
        )

        return self._vehicle_to_dict(vehicle)

    async def deactivate_vehicle(
        self,
        *,
        customer_id: int,
        vehicle_id: int,
    ) -> dict[str, Any]:
        """
        Deactivate one of the authenticated customer's vehicles.
        """

        if self.vehicle_service is None:
            raise RuntimeError(
                "Vehicle service is not configured for SmartPark AI."
            )

        vehicle = await self.vehicle_service.deactivate_vehicle(
            vehicle_id=vehicle_id,
            customer_id=customer_id,
        )

        return self._vehicle_to_dict(vehicle)

    async def edit_vehicle(
        self,
        *,
        customer_id: int,
        vehicle_id: int,
        plate_country: str | None = None,
        registration_number: str | None = None,
        nickname: str | None = None,
        make: str | None = None,
        model: str | None = None,
        colour: str | None = None,
        year: int | None = None,
        vehicle_type: str | None = None,
        parking_profile: str | None = None,
    ) -> dict[str, Any]:
        """
        Edit the details of one of the authenticated customer's active vehicles.

        Validation, ownership checks, duplicate-registration checks, and
        persistence are delegated to the existing VehicleService.
        """

        if self.vehicle_service is None:
            raise RuntimeError(
                "Vehicle service is not configured for SmartPark AI."
            )

        update_data: dict[str, Any] = {}

        if plate_country is not None:
            update_data["plate_country"] = plate_country.strip().upper()
        if registration_number is not None:
            update_data["registration_number"] = registration_number.strip()
        if nickname is not None:
            update_data["nickname"] = nickname.strip() or None
        if make is not None:
            update_data["make"] = make.strip()
        if model is not None:
            update_data["model"] = model.strip()
        if colour is not None:
            update_data["colour"] = colour.strip() or None
        if year is not None:
            update_data["year"] = year
        if vehicle_type is not None:
            update_data["vehicle_type"] = VehicleType(str(vehicle_type).upper())
        if parking_profile is not None:
            update_data["parking_profile"] = ParkingProfile(str(parking_profile).upper())

        if not update_data:
            raise ValueError("At least one vehicle detail must be supplied for editing.")

        data = VehicleUpdate(**update_data)

        vehicle = await self.vehicle_service.update_vehicle(
            vehicle_id=vehicle_id,
            customer_id=customer_id,
            data=data,
        )

        return self._vehicle_to_dict(vehicle)

    async def delete_vehicle(
        self,
        *,
        customer_id: int,
        vehicle_id: int,
    ) -> dict[str, Any]:
        """
        Permanently delete one of the authenticated customer's vehicles.

        The existing VehicleService remains authoritative for ownership
        and database referential-integrity rules.
        """

        if self.vehicle_service is None:
            raise RuntimeError(
                "Vehicle service is not configured for SmartPark AI."
            )

        vehicle = await self.vehicle_service.get_vehicle(vehicle_id)

        if vehicle.customer_id != customer_id:
            raise ValueError(
                "You are not authorized to delete this vehicle."
            )

        vehicle_data = self._vehicle_to_dict(vehicle)

        await self.vehicle_service.delete_vehicle(
            vehicle_id=vehicle_id,
            customer_id=customer_id,
        )

        return {
            "deleted": True,
            "vehicle": vehicle_data,
        }

    # ==========================================================
    # Receipt Verification
    # ==========================================================

    async def verify_receipt(
        self,
        *,
        receipt_number: str,
        verification_token: str,
    ) -> dict[str, Any]:
        """
        Verify a SmartPark receipt using the existing ReceiptService
        verification rules.

        The AI must obtain the receipt number and verification token from
        the uploaded receipt/QR code; they are never supplied by the
        authenticated customer context.
        """

        if self.receipt_service is None:
            raise RuntimeError(
                "Receipt service is not configured for SmartPark AI."
            )

        receipt_number = receipt_number.strip()
        verification_token = verification_token.strip()

        if not receipt_number:
            raise ValueError("Receipt number is required for verification.")

        if not verification_token:
            raise ValueError("Verification code is required for verification.")

        try:
            verification = await self.receipt_service.verify_receipt(
                receipt_number=receipt_number,
                verification_token=verification_token,
            )
        except NotFoundException:
            return {
                "valid": False,
                "result": "not_found",
                "receipt_number": receipt_number,
                "message": "No matching SmartPark receipt was found.",
            }

        return {
            "valid": bool(verification.valid),
            "result": "valid" if verification.valid else "invalid",
            "receipt_number": verification.receipt_number,
            "status": verification.status.value
            if hasattr(verification.status, "value")
            else str(verification.status),
            "receipt_type": verification.receipt_type.value
            if hasattr(verification.receipt_type, "value")
            else str(verification.receipt_type),
            "total_amount": str(verification.total_amount),
            "currency": verification.currency,
            "payment_transaction_id": verification.payment_transaction_id,
            "paid_at": (
                verification.paid_at.isoformat()
                if verification.paid_at
                else None
            ),
            "verified_at": verification.verified_at.isoformat(),
        }

    # ==========================================================
    # Customer Loyalty Programme
    # ==========================================================

    async def get_my_loyalty_program(
        self,
        *,
        customer_id: int,
    ) -> dict[str, Any]:
        """
        Return the authenticated customer's loyalty programme details.

        The existing LoyaltyService and LoyaltyRewardService are reused
        so the chatbot reports the same loyalty data and eligibility
        rules used by the application's loyalty APIs.

        The customer ID is supplied by the authenticated backend request
        and is never accepted from the AI model.
        """

        if self.loyalty_service is None:
            raise RuntimeError(
                "Loyalty service is not configured for SmartPark AI."
            )

        if self.loyalty_reward_service is None:
            raise RuntimeError(
                "Loyalty reward service is not configured for SmartPark AI."
            )

        try:
            account = await self.loyalty_service.get_account(
                customer_id,
            )
        except NotFoundException:
            return {
                "account_found": False,
                "message": (
                    "No SmartPark loyalty account was found for "
                    "the authenticated customer."
                ),
                "points_balance": 0,
                "lifetime_points": 0,
                "tier": None,
                "eligible_rewards": [],
                "reward_redemptions": [],
            }

        eligible_rewards = await self.loyalty_reward_service.get_eligible_rewards(
            customer_id,
            limit=100,
            offset=0,
        )

        reward_redemptions = await self.loyalty_reward_service.get_customer_redemptions(
            customer_id,
            limit=100,
            offset=0,
        )

        return {
            "account_found": True,
            "account_id": account.id,
            "points_balance": account.points_balance,
            "lifetime_points": account.lifetime_points,
            "tier": (
                account.tier.value
                if account.tier is not None
                else None
            ),
            "eligible_rewards": [
                {
                    "id": reward.id,
                    "name": reward.name,
                    "description": reward.description,
                    "reward_type": (
                        reward.reward_type.value
                        if reward.reward_type is not None
                        else None
                    ),
                    "points_cost": reward.points_cost,
                    "monetary_value": (
                        str(reward.monetary_value)
                        if reward.monetary_value is not None
                        else None
                    ),
                    "minimum_tier": (
                        reward.minimum_tier.value
                        if reward.minimum_tier is not None
                        else None
                    ),
                    "valid_from": self._loyalty_date_only(
                        reward.valid_from
                    ),
                    "valid_until": self._loyalty_date_only(
                        reward.valid_until
                    ),
                }
                for reward in eligible_rewards
            ],
            "reward_redemptions": [
                {
                    "id": redemption.id,
                    "reward_id": redemption.reward_id,
                    "redemption_reference": redemption.redemption_reference,
                    "points_spent": redemption.points_spent,
                    "status": (
                        redemption.status.value
                        if redemption.status is not None
                        else None
                    ),
                    "redeemed_at": (
                        redemption.created_at.isoformat()
                        if redemption.created_at is not None
                        else None
                    ),
                    "used_at": (
                        redemption.used_at.isoformat()
                        if redemption.used_at is not None
                        else None
                    ),
                    "expires_at": (
                        redemption.expires_at.isoformat()
                        if redemption.expires_at is not None
                        else None
                    ),
                    "description": redemption.description,
                }
                for redemption in reward_redemptions
            ],
        }

    # ==========================================================
    # Customer Reservations
    # ==========================================================

    async def get_user_reservations(
        self,
        *,
        customer_id: int,
        active_only: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Return reservations belonging only to the authenticated
        SmartPark customer.

        Reservation retrieval is delegated to the existing
        ParkingReservationService so overdue reservations are
        expired using the application's existing business rules.
        """

        if self.reservation_service is None:
            raise RuntimeError(
                "Parking reservation service is not configured for SmartPark AI."
            )

        if active_only:
            reservations = (
                await self.reservation_service.get_active_customer_reservations(
                    customer_id,
                )
            )
        else:
            reservations = (
                await self.reservation_service.get_customer_reservations(
                    customer_id,
                )
            )

        return [
            self._reservation_to_dict(reservation)
            for reservation in reservations
        ]

    # ==========================================================
    # Customer Active Parking Session
    # ==========================================================

    async def get_user_active_session(
        self,
        *,
        customer_id: int,
    ) -> dict[str, Any] | None:
        """
        Return the authenticated customer's current active
        parking session, if one exists.

        The existing ParkingSessionService/repository is reused
        so session status and customer filtering remain aligned
        with the application's existing implementation.
        """

        if self.reservation_service is None:
            raise RuntimeError(
                "Parking reservation service is not configured for SmartPark AI."
            )

        sessions = await self.reservation_service.parking_session_service.list_active(
            customer_id=customer_id,
        )

        if not sessions:
            return None

        return self._parking_session_to_dict(sessions[0])

    async def get_user_active_sessions(
        self,
        *,
        customer_id: int,
    ) -> list[dict[str, Any]]:
        """
        Return all active parking sessions belonging to the
        authenticated customer.

        This is intentionally separate from get_user_active_session()
        so the existing single-session chatbot capability remains
        unchanged. It is used when the customer needs to choose
        a specific active session, such as before payment.
        """

        if self.reservation_service is None:
            raise RuntimeError(
                "Parking reservation service is not configured for SmartPark AI."
            )

        sessions = await self.reservation_service.parking_session_service.list_active(
            customer_id=customer_id,
        )

        return [
            self._parking_session_to_dict(session)
            for session in sessions
        ]

    # ==========================================================
    # Find Available Parking
    # ==========================================================

    async def find_available_parking(
        self,
        *,
        facility_id: int,
        ev_required: bool = False,
        accessible_required: bool = False,
        vip_required: bool = False,
        limit: int = 5,
    ) -> dict[str, Any]:
        """
        Find currently available parking bays at a facility.

        Current availability is based on active/reservable bays
        that do not currently have an ACTIVE parking session.
        This is a current-state search; future reservation-period
        conflicts are handled by find_available_reservation_bay.
        """

        facility_result = await self.db.execute(
            select(ParkingFacility).where(
                ParkingFacility.id == facility_id,
                ParkingFacility.is_active.is_(True),
            )
        )

        facility = facility_result.scalar_one_or_none()

        if facility is None:
            return {
                "facility_id": facility_id,
                "facility_found": False,
                "available": False,
                "available_bays": [],
                "count": 0,
            }

        limit = max(1, min(int(limit), 20))

        query = (
            select(ParkingBay)
            .join(
                ParkingZone,
                ParkingZone.id == ParkingBay.zone_id,
            )
            .where(
                ParkingZone.facility_id == facility_id,
                ParkingZone.is_active.is_(True),
                ParkingBay.is_active.is_(True),
                ParkingBay.is_reservable.is_(True),
            )
            .order_by(
                ParkingBay.sort_order,
                ParkingBay.bay_number,
            )
        )

        if ev_required:
            query = query.where(
                ParkingBay.is_ev_charging.is_(True)
            )

        if accessible_required:
            query = query.where(
                ParkingBay.is_accessible.is_(True)
            )

        if vip_required:
            query = query.where(
                ParkingBay.is_vip.is_(True)
            )

        result = await self.db.execute(query)
        candidate_bays = result.scalars().all()

        available_bays: list[dict[str, Any]] = []

        for bay in candidate_bays:
            if self.reservation_service is None:
                raise RuntimeError(
                    "Parking reservation service is not configured for SmartPark AI."
                )

            has_active_session = (
                await self.reservation_service.parking_session_service.has_active_session(
                    bay.id
                )
            )

            if has_active_session:
                continue

            available_bays.append(
                self._bay_to_dict(bay)
            )

            if len(available_bays) >= limit:
                break

        return {
            "facility_id": facility.id,
            "facility_name": facility.name,
            "facility_code": facility.code,
            "available": bool(available_bays),
            "count": len(available_bays),
            "available_bays": available_bays,
        }

    # ==========================================================
    # Navigation
    # ==========================================================

    async def navigate_to_facility(
        self,
        *,
        facility_id: int | None = None,
        facility_name: str | None = None,
        facility_code: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Resolve a SmartPark facility into the information required
        by the frontend/client to navigate to it.

        Facility identity and coordinates come directly from the
        existing facility data; no route or travel time is invented
        by the backend.
        """

        facility = await self.get_facility_details(
            facility_id=facility_id,
            facility_name=facility_name,
            facility_code=facility_code,
        )

        if facility is None:
            return None

        return {
            "facility_id": facility["id"],
            "facility_name": facility["name"],
            "facility_code": facility["code"],
            "address": facility["address"],
            "city": facility["city"],
            "latitude": facility["latitude"],
            "longitude": facility["longitude"],
            "timezone": facility["timezone"],
        }

    # ==========================================================
    # Find Available Reservation Bay
    # ==========================================================

    async def find_available_reservation_bay(
        self,
        *,
        facility_id: int,
        reserved_from: str,
        reserved_until: str,
        ev_required: bool = False,
        accessible_required: bool = False,
        vip_required: bool = False,
    ) -> dict[str, Any] | None:
        """
        Find the first real reservable bay at a facility that is
        available for the requested reservation period.

        A candidate bay must:
            - belong to the requested facility
            - belong to an active zone
            - be active
            - be reservable
            - not have an active parking session
            - not have an overlapping active reservation

        Optional EV, accessibility, and VIP requirements are applied
        before a bay is returned.
        """

        start = self._parse_datetime(reserved_from)
        end = self._parse_datetime(reserved_until)

        if end <= start:
            raise ValueError(
                "reserved_until must be later than reserved_from."
            )

        # ------------------------------------------------------
        # Verify facility
        # ------------------------------------------------------

        facility_result = await self.db.execute(
            select(ParkingFacility).where(
                ParkingFacility.id == facility_id,
                ParkingFacility.is_active.is_(True),
            )
        )

        facility = facility_result.scalar_one_or_none()

        if facility is None:
            return {
                "facility_id": facility_id,
                "facility_found": False,
                "available": False,
                "message": "The requested parking facility was not found or is inactive.",
                "bay": None,
            }

        # ------------------------------------------------------
        # Retrieve suitable master bays.
        # ------------------------------------------------------

        query = (
            select(ParkingBay)
            .join(
                ParkingZone,
                ParkingZone.id == ParkingBay.zone_id,
            )
            .where(
                ParkingZone.facility_id == facility_id,
                ParkingZone.is_active.is_(True),
                ParkingBay.is_active.is_(True),
                ParkingBay.is_reservable.is_(True),
            )
            .order_by(
                ParkingBay.sort_order,
                ParkingBay.bay_number,
            )
        )

        if ev_required:
            query = query.where(
                ParkingBay.is_ev_charging.is_(True)
            )

        if accessible_required:
            query = query.where(
                ParkingBay.is_accessible.is_(True)
            )

        if vip_required:
            query = query.where(
                ParkingBay.is_vip.is_(True)
            )

        result = await self.db.execute(query)
        candidate_bays = result.scalars().all()

        if not candidate_bays:
            return {
                "facility_id": facility.id,
                "facility_name": facility.name,
                "facility_code": facility.code,
                "available": False,
                "message": "No suitable reservable bays were found for the requested requirements.",
                "bay": None,
            }

        # ------------------------------------------------------
        # Check each candidate against live sessions and
        # overlapping reservations.
        # ------------------------------------------------------

        for bay in candidate_bays:
            active_session_result = await self.db.execute(
                select(ParkingSession.id)
                .where(
                    ParkingSession.parking_bay_id == bay.id,
                    ParkingSession.status == SessionStatus.ACTIVE,
                )
                .limit(1)
            )

            if active_session_result.scalar_one_or_none() is not None:
                continue

            conflict_result = await self.db.execute(
                select(ParkingReservation.id)
                .where(
                    ParkingReservation.parking_bay_id == bay.id,
                    ParkingReservation.status.in_(
                        (
                            ReservationStatus.CREATED,
                            ReservationStatus.CONFIRMED,
                        )
                    ),
                    ParkingReservation.reserved_from < end,
                    ParkingReservation.reserved_until > start,
                )
                .limit(1)
            )

            if conflict_result.scalar_one_or_none() is not None:
                continue

            return {
                "facility_id": facility.id,
                "facility_name": facility.name,
                "facility_code": facility.code,
                "available": True,
                "reserved_from": start.isoformat(),
                "reserved_until": end.isoformat(),
                "bay": self._bay_to_dict(bay),
            }

        return {
            "facility_id": facility.id,
            "facility_name": facility.name,
            "facility_code": facility.code,
            "available": False,
            "reserved_from": start.isoformat(),
            "reserved_until": end.isoformat(),
            "message": "No suitable reservable bay is available for the requested period.",
            "bay": None,
        }

    # ==========================================================
    # Create Reservation
    # ==========================================================

    async def create_reservation(
        self,
        *,
        customer_id: int,
        parking_bay_id: int,
        vehicle_id: int | None = None,
        vehicle_registration: str | None = None,
        vehicle_type: str | None = None,
        reserved_from: str,
        reserved_until: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """
        Create an actual parking reservation for the authenticated
        customer using the existing ParkingReservationService.

        The customer ID is supplied by the backend authentication
        context. It is never supplied by the AI model.

        A registered vehicle is supplied using vehicle_id.
        A borrowed / unregistered vehicle is supplied using
        vehicle_registration and vehicle_type, with vehicle_id
        omitted or null.
        """

        if self.reservation_service is None:
            raise RuntimeError(
                "Parking reservation service is not configured for SmartPark AI."
            )

        start = self._parse_datetime(reserved_from)
        end = self._parse_datetime(reserved_until)

        if end <= start:
            raise ValueError(
                "reserved_until must be later than reserved_from."
            )

        # ------------------------------------------------------
        # Re-check the selected bay immediately before creation.
        # This is deliberately performed again because availability
        # may have changed after the AI's previous availability check.
        # The existing reservation service performs its own final
        # validation and conflict check as well.
        # ------------------------------------------------------

        bay = await self.reservation_service.parking_bay_repository.get_by_id(
            parking_bay_id,
        )

        if bay is None:
            raise ValueError(
                "The selected parking bay no longer exists."
            )

        if not bay.is_active:
            raise ValueError(
                "The selected parking bay is no longer active."
            )

        if not bay.is_reservable:
            raise ValueError(
                "The selected parking bay can no longer be reserved."
            )

        active_session = await self.reservation_service.parking_session_service.has_active_session(
            parking_bay_id,
        )

        if active_session:
            raise ValueError(
                "The selected parking bay is currently occupied."
            )

        conflicts = await self.reservation_service.repository.find_conflicting_reservations(
            parking_bay_id=parking_bay_id,
            reserved_from=start,
            reserved_until=end,
        )

        if conflicts:
            raise ValueError(
                "The selected parking bay is already reserved for the requested period."
            )

        # ------------------------------------------------------
        # Resolve the reservation vehicle mode.
        # ------------------------------------------------------

        if vehicle_id is not None:
            # A registered vehicle ID is authoritative. OpenAI may
            # occasionally echo registration/type details alongside the
            # selected vehicle ID; ignore those redundant fields rather
            # than rejecting an otherwise valid registered-vehicle
            # reservation. The reservation service remains responsible
            # for validating the vehicle exists, is active, and belongs
            # to the authenticated customer.
            reservation_data = ParkingReservationCreate(
                parking_bay_id=parking_bay_id,
                vehicle_id=int(vehicle_id),
                reserved_from=start,
                reserved_until=end,
                notes=notes,
            )

        else:
            # --------------------------------------------------
            # Borrowed / unregistered vehicle.
            # --------------------------------------------------

            if not vehicle_registration:
                raise ValueError(
                    "vehicle_registration is required when using "
                    "a borrowed or unregistered vehicle."
                )

            if not vehicle_type:
                raise ValueError(
                    "vehicle_type is required when using a borrowed "
                    "or unregistered vehicle."
                )

            reservation_data = ParkingReservationCreate(
                parking_bay_id=parking_bay_id,
                vehicle_id=None,
                vehicle_registration=str(vehicle_registration).strip().upper(),
                vehicle_type=str(vehicle_type).upper(),
                reserved_from=start,
                reserved_until=end,
                notes=notes,
            )

        reservation = await self.reservation_service.create_reservation(
            data=reservation_data,
            customer_id=customer_id,
        )

        return self._reservation_to_dict(reservation)

    @staticmethod
    def _loyalty_date_only(
        value: datetime | None,
    ) -> str | None:
        """
        Convert a loyalty reward validity timestamp into the
        customer-facing SmartPark calendar date.

        Loyalty reward validity columns are stored as naive UTC
        datetimes.  Treat naive values as UTC before converting to
        the SmartPark (Kenya) timezone so the AI receives the same
        calendar date shown by the customer portal.
        """

        if value is None:
            return None

        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)

        return value.astimezone(SMARTPARK_TIMEZONE).date().isoformat()

    # ==========================================================
    # Search Helpers
    # ==========================================================

    @staticmethod
    def _normalize_search_text(
        value: str | None,
    ) -> str:
        """
        Normalize user/facility names for tolerant matching.

        Normalization:
            - converts to lowercase
            - replaces punctuation with spaces
            - collapses repeated whitespace
            - removes leading/trailing whitespace
        """

        if not value:
            return ""

        normalized = (
            value
            .strip()
            .lower()
        )

        normalized = re.sub(
            r"[^a-z0-9]+",
            " ",
            normalized,
        )

        normalized = re.sub(
            r"\s+",
            " ",
            normalized,
        )

        return normalized.strip()

    # ==========================================================
    # Geographic Helpers
    # ==========================================================

    @staticmethod
    def _calculate_distance_km(
        latitude_1: float,
        longitude_1: float,
        latitude_2: float,
        longitude_2: float,
    ) -> float:
        """
        Calculate the great-circle distance between two
        geographic coordinates using the Haversine formula.

        Returns:
            Distance in kilometres.
        """

        earth_radius_km = 6371.0088

        lat1 = math.radians(
            latitude_1
        )
        lon1 = math.radians(
            longitude_1
        )

        lat2 = math.radians(
            latitude_2
        )
        lon2 = math.radians(
            longitude_2
        )

        delta_lat = lat2 - lat1
        delta_lon = lon2 - lon1

        haversine_a = (
            math.sin(
                delta_lat / 2
            ) ** 2
            + math.cos(lat1)
            * math.cos(lat2)
            * math.sin(
                delta_lon / 2
            ) ** 2
        )

        central_angle = (
            2
            * math.atan2(
                math.sqrt(haversine_a),
                math.sqrt(
                    1 - haversine_a
                ),
            )
        )

        return (
            earth_radius_km
            * central_angle
        )

    @staticmethod
    def _parse_datetime(
        value: str | datetime,
    ) -> datetime:
        """
        Parse an ISO-8601 datetime supplied by the AI tool call.
        """

        if isinstance(value, datetime):
            return value

        normalized = str(value).strip()

        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"

        try:
            return datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(
                "Datetime values must be valid ISO-8601 timestamps."
            ) from exc

    @staticmethod
    def _vehicle_to_dict(
        vehicle: Vehicle,
    ) -> dict[str, Any]:
        """
        Convert a Vehicle ORM object into a JSON-serializable
        dictionary suitable for the AI.
        """

        return {
            "id": vehicle.id,
            "registration_number": vehicle.registration_number,
            "plate_country": vehicle.plate_country,
            "nickname": vehicle.nickname,
            "make": vehicle.make,
            "model": vehicle.model,
            "colour": vehicle.colour,
            "year": vehicle.year,
            "vehicle_type": (
                vehicle.vehicle_type.value
                if vehicle.vehicle_type is not None
                else None
            ),
            "parking_profile": (
                vehicle.parking_profile.value
                if vehicle.parking_profile is not None
                else None
            ),
            "is_default": vehicle.is_default,
            "is_active": vehicle.is_active,
        }

    @staticmethod
    def _parking_session_to_dict(
        session: ParkingSession,
    ) -> dict[str, Any]:
        """
        Convert a ParkingSession ORM object into a
        JSON-serializable dictionary suitable for the AI.
        """

        return {
            "id": session.id,
            "session_number": session.session_number,
            "customer_id": session.customer_id,
            "parking_bay_id": session.parking_bay_id,
            "vehicle_id": session.vehicle_id,
            "vehicle_registration": session.vehicle_registration,
            "vehicle_type": (
                session.vehicle_type.value
                if session.vehicle_type is not None
                else None
            ),
            "billing_type": (
                session.billing_type.value
                if session.billing_type is not None
                else None
            ),
            "status": (
                session.status.value
                if session.status is not None
                else None
            ),
            "session_source": (
                session.session_source.value
                if session.session_source is not None
                else None
            ),
            "entry_method": (
                session.entry_method.value
                if session.entry_method is not None
                else None
            ),
            "entry_time": (
                session.entry_time.isoformat()
                if session.entry_time is not None
                else None
            ),
            "expected_exit_time": (
                session.expected_exit_time.isoformat()
                if session.expected_exit_time is not None
                else None
            ),
            "exit_time": (
                session.exit_time.isoformat()
                if session.exit_time is not None
                else None
            ),
            "duration_minutes": session.duration_minutes,
            "calculated_amount": (
                float(session.calculated_amount)
                if session.calculated_amount is not None
                else None
            ),
            "paid_amount": (
                float(session.paid_amount)
                if session.paid_amount is not None
                else None
            ),
            "payment_status": (
                session.payment_status.value
                if session.payment_status is not None
                else None
            ),
            "paid_at": (
                session.paid_at.isoformat()
                if session.paid_at is not None
                else None
            ),
            "reservation_id": session.reservation_id,
            "notes": session.notes,
        }

    @staticmethod
    def _reservation_to_dict(
        reservation: ParkingReservation,
    ) -> dict[str, Any]:
        """
        Convert a ParkingReservation ORM object into a
        JSON-serializable dictionary suitable for the AI.
        """

        return {
            "id": reservation.id,
            "reservation_number": reservation.reservation_number,
            "customer_id": reservation.customer_id,
            "parking_bay_id": reservation.parking_bay_id,
            "vehicle_id": reservation.vehicle_id,
            "vehicle_registration": reservation.vehicle_registration,
            "vehicle_type": (
                reservation.vehicle_type.value
                if reservation.vehicle_type is not None
                else None
            ),
            "reserved_from": (
                reservation.reserved_from.isoformat()
                if reservation.reserved_from is not None
                else None
            ),
            "reserved_until": (
                reservation.reserved_until.isoformat()
                if reservation.reserved_until is not None
                else None
            ),
            "estimated_amount": (
                float(reservation.estimated_amount)
                if reservation.estimated_amount is not None
                else None
            ),
            "currency": reservation.currency,
            "status": (
                reservation.status.value
                if reservation.status is not None
                else None
            ),
            "expires_at": (
                reservation.expires_at.isoformat()
                if reservation.expires_at is not None
                else None
            ),
            "confirmed_at": (
                reservation.confirmed_at.isoformat()
                if reservation.confirmed_at is not None
                else None
            ),
            "is_active": reservation.is_active,
            "notes": reservation.notes,
        }

    # ==========================================================
    # Serialization Helpers
    # ==========================================================

    @staticmethod
    def _facility_to_dict(
        facility: ParkingFacility,
    ) -> dict[str, Any]:
        """
        Convert a ParkingFacility ORM object into a
        JSON-serializable dictionary suitable for the AI.
        """

        return {
            "id": facility.id,
            "name": facility.name,
            "code": facility.code,
            "facility_type": (
                facility.facility_type.value
                if facility.facility_type is not None
                else None
            ),
            "description": facility.description,
            "country": facility.country,
            "county": facility.county,
            "city": facility.city,
            "address": facility.address,
            "postal_code": facility.postal_code,
            "latitude": facility.latitude,
            "longitude": facility.longitude,
            "timezone": facility.timezone,
            "opening_time": (
                facility.opening_time.isoformat()
                if facility.opening_time is not None
                else None
            ),
            "closing_time": (
                facility.closing_time.isoformat()
                if facility.closing_time is not None
                else None
            ),
            "is_active": facility.is_active,
        }

    @staticmethod
    def _bay_to_dict(
        bay: ParkingBay,
    ) -> dict[str, Any]:
        """
        Convert a ParkingBay ORM object into a
        JSON-serializable dictionary suitable for the AI.
        """

        return {
            "id": bay.id,
            "zone_id": bay.zone_id,
            "bay_number": bay.bay_number,
            "code": bay.code,
            "bay_type": (
                bay.bay_type.value
                if bay.bay_type is not None
                else None
            ),
            "vehicle_type": (
                bay.vehicle_type.value
                if bay.vehicle_type is not None
                else None
            ),
            "size": (
                bay.size.value
                if bay.size is not None
                else None
            ),
            "is_accessible": bay.is_accessible,
            "is_ev_charging": bay.is_ev_charging,
            "is_vip": bay.is_vip,
            "is_reservable": bay.is_reservable,
            "is_active": bay.is_active,
            "sort_order": bay.sort_order,
            "description": bay.description,
        }