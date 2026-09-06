"""
SmartPark AI Endpoints

API endpoints for the SmartPark AI assistant.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies.auth import (
    get_current_active_user,
)
from app.api.dependencies.services import (
    SmartParkChatServiceDep,
)

from app.models.user import User

from app.schemas.ai_chat import (
    AIChatRequest,
    AIChatResponse,
)


router = APIRouter(
    prefix="/ai",
    tags=["SmartPark AI"],
)


# ==========================================================
# Current Authenticated User
# ==========================================================

CurrentUserDep = Annotated[
    User,
    Depends(get_current_active_user),
]


# ==========================================================
# AI Chat
# ==========================================================


@router.post(
    "/chat",
    response_model=AIChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat with SmartPark AI",
)
async def chat_with_smartpark_ai(
    data: AIChatRequest,
    chat_service: SmartParkChatServiceDep,
    current_user: CurrentUserDep,
) -> AIChatResponse:
    """
    Send a message to SmartPark AI and receive a response.

    The endpoint requires an authenticated active SmartPark
    user. The authenticated user's ID is supplied internally
    to the AI chat service so reservation-related operations
    can always be performed on behalf of the authenticated
    customer.

    Optional latitude and longitude values can be supplied by
    the frontend when the user's browser location is available.

    The optional previous_response_id allows the frontend to
    maintain conversational continuity across separate HTTP
    requests using the OpenAI Responses API.
    """

    try:
        response = await chat_service.chat_with_response_id(
            message=data.message.strip(),
            latitude=data.latitude,
            longitude=data.longitude,
            customer_id=current_user.id,
            previous_response_id=data.previous_response_id,
        )

        return AIChatResponse(
            message=response.message,
            response_id=response.response_id,
        )

    except Exception as exc:
        print(
            f"[SmartPark AI] OpenAI request failed: "
            f"{type(exc).__name__}: {exc}"
        )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="SmartPark AI is temporarily unavailable.",
        ) from exc