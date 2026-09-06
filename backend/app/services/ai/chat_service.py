"""
SmartPark AI Chat Service

Service responsible for communicating with OpenAI and
coordinating SmartPark data and reservation tools.

The AI assistant can use trusted SmartPark tools to retrieve
facility, bay, availability, vehicle, and reservation
information from the application database.

State-changing reservation operations are only performed
through the controlled SmartPark reservation service/tool
layer after the user has explicitly confirmed the reservation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI

from app.config.settings import settings
from app.services.ai.smartpark_ai_tools import (
    SmartParkAITools,
)


@dataclass(slots=True)
class SmartParkChatResult:
    """Result returned by a SmartPark AI conversation turn."""

    message: str
    response_id: str


class SmartParkChatService:
    """
    Service responsible for SmartPark AI conversations.

    GPT-5.6 Luna may request trusted SmartPark data through
    the registered function tools.

    Read-only tools retrieve information from the SmartPark
    database.

    Reservation tools may perform reservation operations only
    after the AI has collected the required booking information
    and the user has explicitly confirmed the reservation.

    The user's authenticated customer ID is supplied by the
    backend and is never accepted from the AI or frontend.
    """

    def __init__(
        self,
        tools: SmartParkAITools,
    ) -> None:
        """
        Create a SmartPark AI Chat Service.

        Args:
            tools:
                SmartPark database and reservation tools.
        """

        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=60.0,
        )

        self.model = settings.OPENAI_MODEL

        self.tools = tools

    # ==========================================================
    # Chat
    # ==========================================================

    async def chat_with_response_id(
        self,
        message: str,
        latitude: float | None = None,
        longitude: float | None = None,
        customer_id: int | None = None,
        previous_response_id: str | None = None,
    ) -> SmartParkChatResult:
        """
        Send a user message to OpenAI and process any requested
        SmartPark tool calls before returning the final answer.

        Latitude and longitude are optional.

        When supplied by the frontend, they represent the user's
        current browser location and are automatically made
        available to the AI for nearest-facility queries.

        customer_id is supplied by the authenticated backend
        request and is used internally for customer-specific
        operations such as retrieving vehicles and creating
        reservations.

        previous_response_id is the response ID returned by the
        previous conversation turn. When supplied, it allows the
        OpenAI Responses API to preserve conversational context
        across separate HTTP requests.
        """

        # ------------------------------------------------------
        # Authoritative Current Date / Time Context
        # ------------------------------------------------------
        # Resolve relative dates against the application's actual
        # Nairobi date/time rather than the model's internal clock.
        # This is generated on every request and is also placed in
        # the top-level instructions so it remains authoritative when
        # a conversation continues with previous_response_id.
        # ------------------------------------------------------

        smartpark_timezone = ZoneInfo("Africa/Nairobi")
        current_datetime = datetime.now(smartpark_timezone)
        today_date = current_datetime.date()
        tomorrow_date = today_date + timedelta(days=1)
        yesterday_date = today_date - timedelta(days=1)

        current_datetime_context = (
            "AUTHORITATIVE CURRENT DATE AND TIME CONTEXT:\n"
            f"Current date: {today_date.isoformat()}\n"
            f"Current day: {current_datetime.strftime('%A')}\n"
            f"Current time: {current_datetime.strftime('%H:%M:%S')}\n"
            "Timezone: Africa/Nairobi (EAT, UTC+03:00)\n"
            f"Today: {today_date.isoformat()}\n"
            f"Tomorrow: {tomorrow_date.isoformat()}\n"
            f"Yesterday: {yesterday_date.isoformat()}\n\n"
            "DATE INTERPRETATION RULES:\n"
            "1. Treat this current date/time context as authoritative for relative date expressions.\n"
            "2. When the user says 'today', use the exact Today date provided above. Never substitute a date from your own knowledge or training.\n"
            "3. When the user says 'tomorrow', use the exact Tomorrow date provided above.\n"
            "4. When the user says 'yesterday', use the exact Yesterday date provided above.\n"
            "5. Resolve weekday expressions such as 'Monday', 'Saturday', or 'this Saturday' using the authoritative current date above. If the intended occurrence is genuinely ambiguous, ask the user to clarify rather than guessing.\n"
            "6. For reservations, convert relative dates into an exact calendar date before checking availability.\n"
            "7. Do not ask the user to confirm the meaning of 'today' when the authoritative date context already resolves it.\n"
            "8. If the user supplies an explicit calendar date, use that date instead of replacing it with the current date.\n"
            "9. Never state that today's date is 24 March 2025 or any other date unless that date is actually supplied by the authoritative current date/time context or by the user.\n\n"
        )

        instructions = current_datetime_context + (
            "CURRENT DATE/TIME OVERRIDE:\n"
            "The SmartPark application has already resolved the current date and time above. Do NOT ask the customer for today's date, the current date, or a YYYY-MM-DD date when the customer uses relative expressions such as 'today'. Resolve those expressions yourself using the authoritative context above. For a reservation, convert 'today' to the exact Today date above before calling any availability or reservation tool.\n\n"
            "You are SmartPark AI, the helpful parking assistant "
            "for the SmartPark parking management system. "
            "\n\n"

            "Be friendly, concise, practical, and conversational. "
            "\n\n"

            "IMPORTANT SMARTPARK DATA RULES:"
            "\n"

            "1. Never invent SmartPark facilities, parking bays, "
            "availability, occupancy, locations, operating hours, "
            "vehicle information, reservation information, prices, "
            "reservation numbers, or other SmartPark data."
            "\n"

            "2. When the user asks about actual SmartPark facilities, "
            "bays, EV charging, current parking availability, their "
            "vehicles, or reservations, use the appropriate SmartPark "
            "data tool."
            "\n"

            "3. Treat tool results as the source of truth for "
            "SmartPark-specific information."
            "\n"

            "4. When the user gives a facility name, first use "
            "get_facilities to resolve the facility to its actual "
            "SmartPark facility ID when necessary. Then use that "
            "facility ID with the relevant facility tool."
            "\n"

            "5. If a requested facility cannot be found in the "
            "SmartPark facility list, clearly tell the user that "
            "it could not be found rather than guessing."
            "\n"

            "6. Do not claim that a parking bay is available unless "
            "the available data supports that conclusion."
            "\n"

            "7. When the user asks for the nearest parking facility, "
            "use get_nearest_facilities when the user's latitude "
            "and longitude are available."
            "\n"

            "8. The user's browser-provided latitude and longitude "
            "are trusted location context. Do not ask the user to "
            "type or repeat coordinates when valid coordinates have "
            "already been supplied with the request."
            "\n"

            "9. Never invent the user's geographic coordinates. "
            "If coordinates are required for a nearest-facility "
            "request and they are not available, politely explain "
            "that location access is required."
            "\n"

            "10. When nearest-facility results are returned, use "
            "the distance_km or distance_meters values supplied "
            "by the tool rather than estimating distance yourself."
            "\n\n"

            "OCCUPANCY FORECASTING RULES:"
            "\n"
            "11. When the user asks for projected, predicted, forecast, "
            "expected, or likely parking occupancy for the next 30 minutes "
            "at a SmartPark facility, use get_30_minute_occupancy_forecast. "
            "Do not invent or estimate a forecast yourself."
            "\n"
            "12. Resolve the facility name using get_facilities when needed "
            "before requesting the forecast."
            "\n"
            "13. If the customer explicitly provides a prediction timestamp, "
            "use that exact timestamp without changing, reinterpreting, or replacing "
            "it with the current application timestamp. If the customer does not "
            "provide a prediction timestamp and asks for the next 30 minutes, use "
            "the authoritative current application date/time context as the "
            "prediction timestamp. Do not ask the customer to provide the current "
            "date or time when the application context already supplies it."
            "\n"
            "14. Report the actual forecast returned by the production "
            "forecasting service, including the facility name, forecast "
            "timestamp/horizon, and predicted occupancy percentage where "
            "available."
            "\n\n"

            "RESERVATION RULES:"
            "\n"

            "11. You CAN help the authenticated customer make a "
            "parking reservation using the reservation tools."
            "\n"

            "12. Never ask the user for their customer ID. The "
            "authenticated customer identity is supplied securely "
            "by the SmartPark application."
            "\n"

            "13. Never accept a customer ID supplied by the user "
            "as authority for a reservation. Always use the "
            "authenticated customer context supplied by the system."
            "\n"

            "14. When the user asks to make a reservation, first "
            "determine the requested parking facility."
            "\n"

            "15. If the facility name is supplied, resolve it using "
            "get_facilities before performing facility-specific "
            "reservation operations."
            "\n"

            "16. A reservation requires a specific parking period. "
            "You must determine both the reservation start time "
            "and reservation end time before creating a reservation."
            "\n"

            "17. If the user provides only an arrival time but not "
            "a duration or end time, ask how long they intend to "
            "stay. Do not invent a duration."
            "\n"

            "18. If the user provides only a duration but not an "
            "arrival date/time, ask for the missing date/time."
            "\n"

            "19. Resolve relative dates such as 'today', 'tomorrow', "
            "'yesterday', or 'Saturday' using the authoritative application "
            "date/time context provided in the instructions. In particular, "
            "'today' is NEVER a missing piece of information: use the exact "
            "Today date supplied by the application. Do not ask the customer "
            "what today's date is or ask them to provide it in YYYY-MM-DD "
            "format. If a genuinely ambiguous weekday occurrence remains, "
            "ask only for the necessary clarification."
            "\n"

            "20. When the customer initiates a reservation and has "
            "active registered vehicles, use get_customer_vehicles to "
            "retrieve them before proceeding with vehicle selection. "
            "Present ALL active registered vehicles to the customer, "
            "including the default vehicle, and clearly mark the default "
            "vehicle as 'Default'. Do not silently select the default "
            "vehicle."
            "\n"

            "21. Unless the customer has already explicitly identified "
            "a specific registered vehicle, ask the customer to choose "
            "which registered vehicle to use, OR to use a borrowed / "
            "unregistered vehicle. The numbered selection_number values "
            "returned by get_customer_vehicles may be used for the "
            "customer's choice. If the customer explicitly chooses the "
            "default vehicle, use the vehicle marked is_default=true. "
            "The default status alone does not constitute customer "
            "confirmation of the vehicle choice."
            "\n"

            "22. If the customer chooses a registered vehicle by number, "
            "registration number, nickname, or other unambiguous vehicle "
            "detail, use the corresponding vehicle's actual id as "
            "vehicle_id. Do not invent, substitute, or silently change "
            "the selected vehicle."
            "\n"

            "23. Borrowed / unregistered vehicles ARE supported. If "
            "the customer explicitly says the vehicle is borrowed, "
            "temporary, new but not registered, or otherwise not in "
            "their SmartPark profile, do NOT reject the reservation "
            "and do NOT tell them to register it first. Instead, use "
            "the vehicle's registration number and vehicle type as "
            "the reservation vehicle. The vehicle_id must be omitted "
            "for this mode."
            "\n"

            "24. A borrowed / unregistered vehicle requires both "
            "its registration number and vehicle type. If the user "
            "provides the registration but not the vehicle type, ask "
            "only for the vehicle type before creating the reservation. "
            "Do not guess the vehicle type."
            "\n"

            "25. Never use a vehicle belonging to another customer. "
            "A borrowed vehicle is represented as a temporary vehicle "
            "and is not treated as a registered customer vehicle."
            "\n"

            "26. Before creating a reservation, use "
            "find_available_reservation_bay to identify a suitable "
            "reservable bay for the requested facility and period."
            "\n"

            "27. Do not assume that a bay that is currently free "
            "will remain available for a future reservation period. "
            "Use the reservation-period availability tool."
            "\n"

            "28. If the user requests EV charging, accessibility, "
            "VIP parking, or another supported bay characteristic, "
            "apply the corresponding requirement when searching "
            "for a bay."
            "\n"

            "29. If no suitable bay is available for the requested "
            "period, tell the customer that no suitable bay is "
            "available and, where useful, ask whether they would "
            "like to try another time."
            "\n"

            "30. NEVER call create_reservation merely because the "
            "user expressed an intention to reserve."
            "\n"

            "31. Before create_reservation is called, present a "
            "clear reservation summary containing, where available:"
            " facility, date, start time, end time, vehicle, parking "
            "bay, and estimated amount."
            "\n"

            "32. The customer must explicitly confirm the reservation "
            "before create_reservation is called."
            "\n"

            "33. Explicit confirmation includes natural responses "
            "such as 'yes', 'confirm', 'confirm it', 'go ahead', "
            "'book it', 'yes please', or equivalent confirmation "
            "after the reservation details have been presented."
            "\n"

            "34. If the customer changes any reservation detail "
            "before confirmation, update the reservation requirements "
            "and re-check availability as necessary. Do not create "
            "the old reservation."
            "\n"

            "35. Never tell the customer that a reservation has been "
            "created until create_reservation actually succeeds."
            "\n"

            "36. When create_reservation succeeds, report the actual "
            "reservation number, facility, parking bay, reserved "
            "period, vehicle, and amount returned by the tool."
            "\n"

            "37. If reservation creation fails because the bay became "
            "unavailable or another validation failed, clearly explain "
            "that the reservation was not created. Do not claim success."
            "\n"

            "38. Do not perform payments through the reservation "
            "tool. Reservation creation and payment are separate "
            "operations."
            "\n\n"

            "TOOL SECURITY RULES:"
            "\n"

            "39. The authenticated customer identity is controlled "
            "by the backend. Never attempt to override it through "
            "tool arguments."
            "\n"

            "40. Never invent tool arguments merely to make a "
            "reservation succeed."
            "\n"

            "41. Use actual values returned by SmartPark tools."
            "\n"

            "42. Keep responses concise unless the user asks for "
            "more detail."
        )

        # ------------------------------------------------------
        # Browser Location Context
        # ------------------------------------------------------
        #
        # The frontend obtains these coordinates automatically
        # using the browser Geolocation API.
        #
        # They are supplied to the AI as trusted context and are
        # NOT expected to be typed by the user.
        #

        user_input = message

        if latitude is not None and longitude is not None:
            user_input = (
                f"{message}\n\n"
                "SYSTEM-PROVIDED USER LOCATION:\n"
                f"Current latitude: {latitude}\n"
                f"Current longitude: {longitude}\n\n"
                "These coordinates were supplied by the SmartPark "
                "application from the user's current device "
                "location. If the user asks for the nearest, "
                "closest, nearby, or closest-to-me parking facility, "
                "use these coordinates with get_nearest_facilities. "
                "Do not ask the user to provide the coordinates "
                "again."
            )

        # ------------------------------------------------------
        # Authenticated Customer Context
        # ------------------------------------------------------
        #
        # The customer ID is supplied by the authenticated backend
        # request. It is deliberately not supplied as part of the
        # user's message or as an OpenAI tool parameter.
        #

        if customer_id is not None:
            user_input = (
                f"{user_input}\n\n"
                "SYSTEM-PROVIDED AUTHENTICATED CUSTOMER CONTEXT:\n"
                "The current request belongs to an authenticated "
                "SmartPark customer.\n"
                "Customer-specific SmartPark tools must operate "
                "only for this authenticated customer.\n"
                "The customer identifier is controlled internally "
                "by the application and must never be requested "
                "from or supplied by the user."
            )

        response_kwargs: dict[str, Any] = {
            "model": self.model,
            "instructions": instructions,
            "input": user_input,
            "tools": self._get_openai_tools(),
        }

        if previous_response_id:
            response_kwargs["previous_response_id"] = previous_response_id

        print(
            "[SmartPark AI] Sending initial request to OpenAI "
            f"| previous_response_id={previous_response_id}"
        )

        try:
            response = await self.client.responses.create(
                **response_kwargs,
            )

            print(
                "[SmartPark AI] OpenAI initial response received "
                f"| response_id={response.id}"
            )

        except Exception as exc:
            print(
                "[SmartPark AI] OpenAI initial request failed: "
                f"{type(exc).__name__}: {exc}"
            )
            raise

        # ======================================================
        # Tool-calling loop
        # ======================================================

        while True:
            tool_calls = [
                item
                for item in response.output
                if getattr(item, "type", None)
                == "function_call"
            ]

            if not tool_calls:
                return SmartParkChatResult(
                    message=response.output_text,
                    response_id=response.id,
                )

            tool_outputs: list[dict[str, Any]] = []

            for tool_call in tool_calls:
                tool_name = tool_call.name

                try:
                    arguments = json.loads(
                        tool_call.arguments
                    )

                    print(
                        "[SmartPark AI] Tool call: "
                        f"{tool_name} | "
                        f"arguments={arguments}"
                    )

                    # --------------------------------------------------
                    # IMPORTANT:
                    # For nearest-facility requests, if browser
                    # coordinates are available, ensure the tool uses
                    # those coordinates rather than coordinates
                    # invented or omitted by the model.
                    # --------------------------------------------------

                    if (
                        tool_name == "get_nearest_facilities"
                        and latitude is not None
                        and longitude is not None
                    ):
                        arguments["latitude"] = latitude
                        arguments["longitude"] = longitude

                    # --------------------------------------------------
                    # IMPORTANT:
                    # Customer identity for customer-specific tools
                    # comes exclusively from the authenticated backend
                    # request. It is never taken from OpenAI arguments.
                    # --------------------------------------------------

                    result = await self._execute_tool(
                        tool_name=tool_name,
                        arguments=arguments,
                        customer_id=customer_id,
                    )

                    tool_output = json.dumps(
                        result,
                        default=str,
                    )

                except Exception as exc:
                    print(
                        "[SmartPark AI] Tool execution failed: "
                        f"{tool_name} | "
                        f"{type(exc).__name__}: {exc}"
                    )

                    tool_output = json.dumps(
                        {
                            "error": (
                                "The requested SmartPark operation "
                                "could not be completed."
                            ),
                            "operation": tool_name,
                        }
                    )

                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": tool_output,
                    }
                )

            # --------------------------------------------------
            # Send tool results back to OpenAI
            # --------------------------------------------------

            previous_tool_response_id = response.id

            print(
                "[SmartPark AI] Sending tool results to OpenAI "
                f"| previous_response_id={previous_tool_response_id} "
                f"| tool_outputs={len(tool_outputs)}"
            )

            try:
                response = await self.client.responses.create(
                    model=self.model,
                    instructions=instructions,
                    previous_response_id=previous_tool_response_id,
                    input=tool_outputs,
                    tools=self._get_openai_tools(),
                )

                print(
                    "[SmartPark AI] OpenAI tool-result response received "
                    f"| response_id={response.id}"
                )

            except Exception as exc:
                print(
                    "[SmartPark AI] OpenAI tool-result request failed: "
                    f"{type(exc).__name__}: {exc}"
                )
                raise

    async def chat(
        self,
        message: str,
        latitude: float | None = None,
        longitude: float | None = None,
        customer_id: int | None = None,
    ) -> str:
        """
        Backward-compatible chat method returning only the AI text.

        Existing callers that do not need the OpenAI response ID can
        continue using this method. New conversational callers should
        use chat_with_response_id().
        """

        result = await self.chat_with_response_id(
            message=message,
            latitude=latitude,
            longitude=longitude,
            customer_id=customer_id,
            previous_response_id=None,
        )

        return result.message

    # ==========================================================
    # OpenAI Tool Definitions
    # ==========================================================

    @staticmethod
    def _get_openai_tools() -> list[dict[str, Any]]:
        """
        Return the SmartPark functions exposed to GPT-5.6 Luna.
        """

        return [
            # --------------------------------------------------
            # Get Facilities
            # --------------------------------------------------

            {
                "type": "function",
                "name": "get_facilities",
                "description": (
                    "Retrieve the SmartPark parking facilities "
                    "from the database. Use this whenever the "
                    "user asks about available parking facilities "
                    "or when a facility name needs to be resolved "
                    "to its SmartPark facility ID."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "active_only": {
                            "type": "boolean",
                            "description": (
                                "Whether to return only active "
                                "parking facilities. Defaults "
                                "to true."
                            ),
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },

            # --------------------------------------------------
            # Get Facility Details
            # --------------------------------------------------

            {
                "type": "function",
                "name": "get_facility_details",
                "description": (
                    "Retrieve detailed information about a "
                    "specific SmartPark parking facility. "
                    "Prefer using the facility ID returned by "
                    "get_facilities. The facility may also be "
                    "identified by name or code."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "facility_id": {
                            "type": "integer",
                            "description": (
                                "SmartPark facility ID, when known. "
                                "Prefer this identifier when "
                                "available."
                            ),
                        },
                        "facility_name": {
                            "type": "string",
                            "description": (
                                "Name or partial name of the "
                                "parking facility, when its "
                                "facility ID is not known."
                            ),
                        },
                        "facility_code": {
                            "type": "string",
                            "description": (
                                "Unique SmartPark facility code, "
                                "when known."
                            ),
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },

            # --------------------------------------------------
            # Get Facility Bays
            # --------------------------------------------------

            {
                "type": "function",
                "name": "get_facility_bays",
                "description": (
                    "Retrieve parking bays belonging to a "
                    "specific SmartPark facility. Use the "
                    "facility ID returned by get_facilities "
                    "when the user provides a facility name. "
                    "Can be filtered for EV charging, "
                    "accessibility, VIP status, or reservability."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "facility_id": {
                            "type": "integer",
                            "description": (
                                "SmartPark facility ID."
                            ),
                        },
                        "active_only": {
                            "type": "boolean",
                            "description": (
                                "Whether to return only active "
                                "bays. Defaults to true."
                            ),
                        },
                        "ev_only": {
                            "type": "boolean",
                            "description": (
                                "Return only EV charging bays."
                            ),
                        },
                        "accessible_only": {
                            "type": "boolean",
                            "description": (
                                "Return only accessible bays."
                            ),
                        },
                        "vip_only": {
                            "type": "boolean",
                            "description": (
                                "Return only VIP bays."
                            ),
                        },
                        "reservable_only": {
                            "type": "boolean",
                            "description": (
                                "Return only reservable bays."
                            ),
                        },
                    },
                    "required": [
                        "facility_id"
                    ],
                    "additionalProperties": False,
                },
            },

            # --------------------------------------------------
            # Get Facility Availability
            # --------------------------------------------------

            {
                "type": "function",
                "name": "get_facility_availability",
                "description": (
                    "Retrieve the current parking availability "
                    "for a SmartPark facility. Use the facility "
                    "ID returned by get_facilities when the user "
                    "provides a facility name. The result includes "
                    "total active bays, occupied bays, available "
                    "bays, and occupancy percentages."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "facility_id": {
                            "type": "integer",
                            "description": (
                                "SmartPark facility ID."
                            ),
                        },
                    },
                    "required": [
                        "facility_id"
                    ],
                    "additionalProperties": False,
                },
            },

            # --------------------------------------------------
            # Get Nearest Facilities
            # --------------------------------------------------

            {
                "type": "function",
                "name": "get_nearest_facilities",
                "description": (
                    "Find the nearest SmartPark parking facilities "
                    "to a supplied geographic coordinate. Use this "
                    "when the user asks for nearby, nearest, closest, "
                    "or closest-to-me parking facilities. When "
                    "SmartPark application location context is "
                    "provided, use that location. Results are "
                    "ordered from nearest to farthest and include "
                    "distance in kilometres and metres."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "latitude": {
                            "type": "number",
                            "description": (
                                "Current/user latitude in decimal "
                                "degrees, between -90 and 90."
                            ),
                        },
                        "longitude": {
                            "type": "number",
                            "description": (
                                "Current/user longitude in decimal "
                                "degrees, between -180 and 180."
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "description": (
                                "Maximum number of nearby "
                                "facilities to return. Defaults "
                                "to 5 and should normally remain "
                                "between 1 and 20."
                            ),
                        },
                        "active_only": {
                            "type": "boolean",
                            "description": (
                                "Whether to return only active "
                                "parking facilities. Defaults "
                                "to true."
                            ),
                        },
                    },
                    "required": [
                        "latitude",
                        "longitude"
                    ],
                    "additionalProperties": False,
                },
            },

            # ==================================================
            # Occupancy Forecasting Tools
            # ==================================================

            # --------------------------------------------------
            # Get 30-Minute Occupancy Forecast
            # --------------------------------------------------

            {
                "type": "function",
                "name": "get_30_minute_occupancy_forecast",
                "description": (
                    "Generate the production 30-minute parking occupancy "
                    "forecast for a SmartPark parking facility. Use this "
                    "when the customer asks for projected, predicted, "
                    "forecast, expected, or likely occupancy over the next "
                    "30 minutes. If the customer explicitly provides a prediction "
                    "timestamp, use that exact timestamp. Otherwise, for a normal "
                    "next-30-minute request, use the authoritative current "
                    "application timestamp supplied in the SmartPark instructions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "facility_id": {
                            "type": "integer",
                            "description": (
                                "SmartPark facility ID returned by "
                                "get_facilities."
                            ),
                        },
                        "prediction_timestamp": {
                            "type": "string",
                            "description": (
                                "ISO-8601 timezone-aware prediction "
                                "timestamp. Use the customer's explicitly "
                                "supplied timestamp when one is provided. "
                                "Otherwise, for a next-30-minute request, use "
                                "the authoritative current application "
                                "date/time supplied in the instructions."
                            ),
                        },
                        "lookback_minutes": {
                            "type": "integer",
                            "description": (
                                "Historical observation window in minutes. "
                                "Use the production default of 1440 minutes "
                                "(24 hours) unless a different supported "
                                "value is explicitly required."
                            ),
                        },
                    },
                    "required": [
                        "facility_id",
                        "prediction_timestamp",
                    ],
                    "additionalProperties": False,
                },
            },

            # ==================================================
            # Reservation Tools
            # ==================================================

            # --------------------------------------------------
            # Get Customer Vehicles
            # --------------------------------------------------

            {
                "type": "function",
                "name": "get_customer_vehicles",
                "description": (
                    "Retrieve the authenticated SmartPark "
                    "customer's active registered vehicles. "
                    "Use this at the start of a reservation vehicle "
                    "selection flow. Return all active registered "
                    "vehicles, including the default vehicle, with "
                    "numbered selections so the customer can choose "
                    "a registered vehicle or a borrowed/unregistered "
                    "vehicle. Never request or supply a customer ID."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },

            # --------------------------------------------------
            # Find Available Reservation Bay
            # --------------------------------------------------

            {
                "type": "function",
                "name": "find_available_reservation_bay",
                "description": (
                    "Find a real reservable parking bay at a "
                    "SmartPark facility for a requested reservation "
                    "period. The result must account for existing "
                    "reservations and active parking sessions. "
                    "Use this before creating a reservation. "
                    "Optional filters can require EV charging, "
                    "accessibility, or VIP parking."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "facility_id": {
                            "type": "integer",
                            "description": (
                                "SmartPark facility ID."
                            ),
                        },
                        "reserved_from": {
                            "type": "string",
                            "description": (
                                "Reservation start datetime in "
                                "ISO-8601 format."
                            ),
                        },
                        "reserved_until": {
                            "type": "string",
                            "description": (
                                "Reservation end datetime in "
                                "ISO-8601 format."
                            ),
                        },
                        "ev_required": {
                            "type": "boolean",
                            "description": (
                                "Whether the customer requires "
                                "an EV charging bay."
                            ),
                        },
                        "accessible_required": {
                            "type": "boolean",
                            "description": (
                                "Whether the customer requires "
                                "an accessible parking bay."
                            ),
                        },
                        "vip_required": {
                            "type": "boolean",
                            "description": (
                                "Whether the customer requires "
                                "a VIP parking bay."
                            ),
                        },
                    },
                    "required": [
                        "facility_id",
                        "reserved_from",
                        "reserved_until",
                    ],
                    "additionalProperties": False,
                },
            },

            # --------------------------------------------------
            # Create Reservation
            # --------------------------------------------------

            {
                "type": "function",
                "name": "create_reservation",
                "description": (
                    "Create an actual SmartPark parking reservation "
                    "for the authenticated customer. This is a "
                    "state-changing operation. ONLY call this "
                    "after all required reservation details have "
                    "been collected, availability has been checked, "
                    "a reservation summary has been presented to "
                    "the customer, and the customer has explicitly "
                    "confirmed the reservation."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "parking_bay_id": {
                            "type": "integer",
                            "description": (
                                "The actual SmartPark parking bay "
                                "ID returned by the availability "
                                "tool."
                            ),
                        },
                        "vehicle_id": {
                            "type": "integer",
                            "description": (
                                "The authenticated customer's registered "
                                "vehicle ID. Omit or set to null when using "
                                "a borrowed or unregistered vehicle."
                            ),
                        },
                        "vehicle_registration": {
                            "type": "string",
                            "description": (
                                "Vehicle registration number for a borrowed "
                                "or unregistered vehicle. Required when "
                                "vehicle_id is omitted or null."
                            ),
                        },
                        "vehicle_type": {
                            "type": "string",
                            "description": (
                                "Vehicle type for a borrowed or unregistered "
                                "vehicle. Required when vehicle_id is omitted "
                                "or null."
                            ),
                        },
                        "reserved_from": {
                            "type": "string",
                            "description": (
                                "Reservation start datetime in "
                                "ISO-8601 format."
                            ),
                        },
                        "reserved_until": {
                            "type": "string",
                            "description": (
                                "Reservation end datetime in "
                                "ISO-8601 format."
                            ),
                        },
                        "notes": {
                            "type": "string",
                            "description": (
                                "Optional reservation notes."
                            ),
                        },
                    },
                    "required": [
                        "parking_bay_id",
                        "reserved_from",
                        "reserved_until",
                    ],
                    "additionalProperties": False,
                },
            },
        ]

    # ==========================================================
    # Tool Execution
    # ==========================================================

    async def _execute_tool(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        customer_id: int | None = None,
    ) -> Any:
        """
        Execute a SmartPark tool requested by GPT-5.6 Luna.

        Facility names are resolved against the live facility
        list before facility-specific operations are executed.

        Customer-specific operations receive the authenticated
        customer ID from the backend rather than accepting one
        from the model.
        """

        # ------------------------------------------------------
        # Get Facilities
        # ------------------------------------------------------

        if tool_name == "get_facilities":
            return await self.tools.get_facilities(
                active_only=arguments.get(
                    "active_only",
                    True,
                ),
            )

        # ------------------------------------------------------
        # Get Facility Details
        # ------------------------------------------------------

        if tool_name == "get_facility_details":
            facility_id = arguments.get(
                "facility_id"
            )

            facility_name = arguments.get(
                "facility_name"
            )

            facility_code = arguments.get(
                "facility_code"
            )

            # --------------------------------------------------
            # If Luna supplied a facility name but no ID,
            # resolve the name from the known facility list first.
            # --------------------------------------------------

            if (
                facility_id is None
                and facility_name
            ):
                facility_id = await self._resolve_facility_id(
                    facility_name=facility_name,
                )

            # --------------------------------------------------
            # If Luna supplied a code but no ID, resolve it.
            # --------------------------------------------------

            if (
                facility_id is None
                and facility_code
            ):
                facility_id = await self._resolve_facility_id(
                    facility_code=facility_code,
                )

            # --------------------------------------------------
            # Prefer ID-based lookup.
            # --------------------------------------------------

            if facility_id is not None:
                return await self.tools.get_facility_details(
                    facility_id=facility_id,
                )

            # --------------------------------------------------
            # Final fallback to direct lookup.
            # --------------------------------------------------

            return await self.tools.get_facility_details(
                facility_id=facility_id,
                facility_name=facility_name,
                facility_code=facility_code,
            )

        # ------------------------------------------------------
        # Get Facility Bays
        # ------------------------------------------------------

        if tool_name == "get_facility_bays":
            facility_id = arguments.get(
                "facility_id"
            )

            if facility_id is None:
                raise ValueError(
                    "facility_id is required for "
                    "get_facility_bays."
                )

            return await self.tools.get_facility_bays(
                facility_id=facility_id,
                active_only=arguments.get(
                    "active_only",
                    True,
                ),
                ev_only=arguments.get(
                    "ev_only",
                    False,
                ),
                accessible_only=arguments.get(
                    "accessible_only",
                    False,
                ),
                vip_only=arguments.get(
                    "vip_only",
                    False,
                ),
                reservable_only=arguments.get(
                    "reservable_only",
                    False,
                ),
            )

        # ------------------------------------------------------
        # Get Facility Availability
        # ------------------------------------------------------

        if tool_name == "get_facility_availability":
            facility_id = arguments.get(
                "facility_id"
            )

            if facility_id is None:
                raise ValueError(
                    "facility_id is required for "
                    "get_facility_availability."
                )

            return await self.tools.get_facility_availability(
                facility_id=facility_id,
            )

        # ------------------------------------------------------
        # Get Nearest Facilities
        # ------------------------------------------------------

        if tool_name == "get_nearest_facilities":
            latitude = arguments.get(
                "latitude"
            )

            longitude = arguments.get(
                "longitude"
            )

            if latitude is None:
                raise ValueError(
                    "latitude is required for "
                    "get_nearest_facilities."
                )

            if longitude is None:
                raise ValueError(
                    "longitude is required for "
                    "get_nearest_facilities."
                )

            return await self.tools.get_nearest_facilities(
                latitude=float(latitude),
                longitude=float(longitude),
                limit=int(
                    arguments.get(
                        "limit",
                        5,
                    )
                ),
                active_only=arguments.get(
                    "active_only",
                    True,
                ),
            )

        # ======================================================
        # Occupancy Forecasting Tools
        # ======================================================

        # ------------------------------------------------------
        # Get 30-Minute Occupancy Forecast
        # ------------------------------------------------------

        if tool_name == "get_30_minute_occupancy_forecast":
            facility_id = arguments.get(
                "facility_id"
            )

            prediction_timestamp = arguments.get(
                "prediction_timestamp"
            )

            if facility_id is None:
                raise ValueError(
                    "facility_id is required for "
                    "get_30_minute_occupancy_forecast."
                )

            if not prediction_timestamp:
                raise ValueError(
                    "prediction_timestamp is required for "
                    "get_30_minute_occupancy_forecast."
                )

            lookback_minutes = arguments.get(
                "lookback_minutes",
                1440,
            )

            return await self.tools.get_30_minute_occupancy_forecast(
                facility_id=int(facility_id),
                prediction_timestamp=datetime.fromisoformat(
                    str(prediction_timestamp).replace(
                        "Z",
                        "+00:00",
                    )
                ),
                lookback_minutes=int(lookback_minutes),
            )

        # ======================================================
        # Reservation Tools
        # ======================================================

        # ------------------------------------------------------
        # Get Customer Vehicles
        # ------------------------------------------------------

        if tool_name == "get_customer_vehicles":
            if customer_id is None:
                raise ValueError(
                    "Authenticated customer context is required "
                    "for get_customer_vehicles."
                )

            return await self.tools.get_customer_vehicles(
                customer_id=customer_id,
            )

        # ------------------------------------------------------
        # Find Available Reservation Bay
        # ------------------------------------------------------

        if tool_name == "find_available_reservation_bay":
            facility_id = arguments.get(
                "facility_id"
            )

            reserved_from = arguments.get(
                "reserved_from"
            )

            reserved_until = arguments.get(
                "reserved_until"
            )

            if facility_id is None:
                raise ValueError(
                    "facility_id is required for "
                    "find_available_reservation_bay."
                )

            if not reserved_from:
                raise ValueError(
                    "reserved_from is required for "
                    "find_available_reservation_bay."
                )

            if not reserved_until:
                raise ValueError(
                    "reserved_until is required for "
                    "find_available_reservation_bay."
                )

            return await self.tools.find_available_reservation_bay(
                facility_id=int(facility_id),
                reserved_from=str(reserved_from),
                reserved_until=str(reserved_until),
                ev_required=arguments.get(
                    "ev_required",
                    False,
                ),
                accessible_required=arguments.get(
                    "accessible_required",
                    False,
                ),
                vip_required=arguments.get(
                    "vip_required",
                    False,
                ),
            )

        # ------------------------------------------------------
        # Create Reservation
        # ------------------------------------------------------

        if tool_name == "create_reservation":
            if customer_id is None:
                raise ValueError(
                    "Authenticated customer context is required "
                    "for create_reservation."
                )

            parking_bay_id = arguments.get(
                "parking_bay_id"
            )

            vehicle_id = arguments.get(
                "vehicle_id"
            )

            # OpenAI may occasionally emit 0 for an optional integer
            # vehicle_id when the reservation is for a borrowed /
            # unregistered vehicle. In SmartPark, 0 is not a valid
            # registered vehicle ID, so treat it exactly like omitted/null
            # and preserve the borrowed-vehicle path below.
            if vehicle_id == 0:
                vehicle_id = None

            vehicle_registration = arguments.get(
                "vehicle_registration"
            )

            vehicle_type = arguments.get(
                "vehicle_type"
            )

            reserved_from = arguments.get(
                "reserved_from"
            )

            reserved_until = arguments.get(
                "reserved_until"
            )

            if parking_bay_id is None:
                raise ValueError(
                    "parking_bay_id is required for "
                    "create_reservation."
                )

            if vehicle_id is None:
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

            # For a registered vehicle, vehicle_id is authoritative.
            # Ignore any redundant registration/type fields the model may
            # have emitted alongside the selected registered vehicle.

            if not reserved_from:
                raise ValueError(
                    "reserved_from is required for "
                    "create_reservation."
                )

            if not reserved_until:
                raise ValueError(
                    "reserved_until is required for "
                    "create_reservation."
                )

            # --------------------------------------------------
            # Explicitly pass only the authenticated customer ID
            # to the reservation operation.
            # --------------------------------------------------

            return await self.tools.create_reservation(
                customer_id=customer_id,
                parking_bay_id=int(parking_bay_id),
                vehicle_id=(
                    int(vehicle_id)
                    if vehicle_id is not None
                    else None
                ),
                vehicle_registration=(
                    str(vehicle_registration).strip().upper()
                    if vehicle_registration is not None
                    else None
                ),
                vehicle_type=(
                    str(vehicle_type).upper()
                    if vehicle_type is not None
                    else None
                ),
                reserved_from=str(reserved_from),
                reserved_until=str(reserved_until),
                notes=arguments.get(
                    "notes"
                ),
            )

        raise ValueError(
            f"Unknown SmartPark AI tool: {tool_name}"
        )

    # ==========================================================
    # Facility Resolution
    # ==========================================================

    async def _resolve_facility_id(
        self,
        *,
        facility_name: str | None = None,
        facility_code: str | None = None,
    ) -> int | None:
        """
        Resolve a facility name or code to its actual SmartPark
        facility ID.

        This deliberately uses get_facilities(), which retrieves
        the live SmartPark facility list successfully.

        Matching strategy:

            1. Exact normalized name
            2. Exact facility code
            3. Normalized partial name
            4. Token-based name match
        """

        facilities = await self.tools.get_facilities(
            active_only=False,
        )

        if not facilities:
            return None

        # ------------------------------------------------------
        # Facility code
        # ------------------------------------------------------

        if facility_code:
            requested_code = (
                str(facility_code)
                .strip()
                .upper()
            )

            for facility in facilities:
                actual_code = str(
                    facility.get("code") or ""
                ).strip().upper()

                if (
                    actual_code
                    and actual_code == requested_code
                ):
                    return facility.get("id")

        # ------------------------------------------------------
        # Facility name
        # ------------------------------------------------------

        if facility_name:
            requested_name = self._normalize_text(
                facility_name
            )

            if not requested_name:
                return None

            # --------------------------------------------------
            # Exact normalized name
            # --------------------------------------------------

            for facility in facilities:
                actual_name = self._normalize_text(
                    str(
                        facility.get("name") or ""
                    )
                )

                if (
                    actual_name
                    and actual_name == requested_name
                ):
                    return facility.get("id")

            # --------------------------------------------------
            # Partial name
            # --------------------------------------------------

            for facility in facilities:
                actual_name = self._normalize_text(
                    str(
                        facility.get("name") or ""
                    )
                )

                if not actual_name:
                    continue

                if (
                    requested_name in actual_name
                    or actual_name in requested_name
                ):
                    return facility.get("id")

            # --------------------------------------------------
            # Token-based matching
            # --------------------------------------------------

            requested_tokens = set(
                requested_name.split()
            )

            best_id: int | None = None
            best_overlap = 0

            for facility in facilities:
                actual_name = self._normalize_text(
                    str(
                        facility.get("name") or ""
                    )
                )

                if not actual_name:
                    continue

                actual_tokens = set(
                    actual_name.split()
                )

                overlap = len(
                    requested_tokens
                    & actual_tokens
                )

                if overlap > best_overlap:
                    best_overlap = overlap
                    best_id = facility.get("id")

            if best_overlap > 0:
                return best_id

        return None

    # ==========================================================
    # Text Normalization
    # ==========================================================

    @staticmethod
    def _normalize_text(
        value: str | None,
    ) -> str:
        """
        Normalize text for facility matching.

        Converts to lowercase and collapses whitespace.
        """

        if not value:
            return ""

        return " ".join(
            str(value)
            .strip()
            .lower()
            .split()
        )