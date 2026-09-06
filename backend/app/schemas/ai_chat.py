"""
SmartPark AI Schemas

Request and response schemas for the SmartPark AI assistant.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ==========================================================
# AI Chat Request
# ==========================================================


class AIChatRequest(BaseModel):
    """
    Request payload for the SmartPark AI chat endpoint.

    Latitude and longitude are optional because not every
    SmartPark AI question requires the user's location.

    When available, the frontend can obtain these coordinates
    from the user's browser geolocation service and send them
    automatically with the chat message.

    Customer identity is intentionally NOT included in this
    request. The authenticated customer's identity is obtained
    securely by the backend from the authenticated user/session.

    previous_response_id is optional and is used to maintain
    conversational continuity across separate HTTP requests
    using the OpenAI Responses API.
    """

    message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="The user's message to SmartPark AI.",
    )

    latitude: float | None = Field(
        default=None,
        ge=-90,
        le=90,
        description=(
            "User's current latitude in decimal degrees, "
            "when browser location is available."
        ),
    )

    longitude: float | None = Field(
        default=None,
        ge=-180,
        le=180,
        description=(
            "User's current longitude in decimal degrees, "
            "when browser location is available."
        ),
    )

    previous_response_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description=(
            "OpenAI Responses API response ID from the previous "
            "turn, used to preserve conversational context."
        ),
    )


# ==========================================================
# AI Chat Response
# ==========================================================


class AIChatResponse(BaseModel):
    """
    Response payload from the SmartPark AI chat endpoint.
    """

    message: str = Field(
        ...,
        description="SmartPark AI's response to the user's message.",
    )

    response_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description=(
            "OpenAI Responses API response ID for this turn. "
            "The frontend should send this value as "
            "previous_response_id on the next message."
        ),
    )