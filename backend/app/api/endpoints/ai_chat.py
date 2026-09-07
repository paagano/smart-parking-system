"""
SmartPark AI Endpoints

API endpoints for the SmartPark AI assistant.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

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

# ==========================================================
# AI Chat With Attachment
# ==========================================================

@router.post(
    "/chat/attachment",
    response_model=AIChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat with SmartPark AI and attachment",
)
async def chat_with_smartpark_ai_attachment(
    chat_service: SmartParkChatServiceDep,
    current_user: CurrentUserDep,
    attachment: UploadFile = File(...),
    message: str = Form(default="Please verify this receipt."),
    latitude: float | None = Form(default=None),
    longitude: float | None = Form(default=None),
    previous_response_id: str | None = Form(default=None),
) -> AIChatResponse:
    """
    Send a SmartPark AI message together with one receipt attachment.

    The existing JSON /ai/chat endpoint is intentionally left unchanged.
    This dedicated multipart endpoint adds receipt attachment support
    without changing the existing chat contract.
    """

    allowed_content_types = {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/webp",
    }

    content_type = (attachment.content_type or "").lower().strip()

    if content_type not in allowed_content_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                "Unsupported attachment type. Please upload a PDF, "
                "JPEG, PNG, or WebP receipt."
            ),
        )

    if not message.strip():
        message = "Please verify this receipt."

    if len(message.strip()) > 4000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Message must not exceed 4000 characters.",
        )

    max_attachment_bytes = 10 * 1024 * 1024
    attachment_bytes = await attachment.read(
        max_attachment_bytes + 1
    )

    if len(attachment_bytes) > max_attachment_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Attachment must not exceed 10 MB.",
        )

    filename = (attachment.filename or "receipt").strip()

    try:
        response = await chat_service.chat_with_response_id(
            message=message.strip(),
            latitude=latitude,
            longitude=longitude,
            customer_id=current_user.id,
            previous_response_id=previous_response_id,
            attachment_bytes=attachment_bytes,
            attachment_filename=filename,
            attachment_content_type=content_type,
        )

        return AIChatResponse(
            message=response.message,
            response_id=response.response_id,
        )

    except HTTPException:
        raise
    except Exception as exc:
        print(
            f"[SmartPark AI] Attachment request failed: "
            f"{type(exc).__name__}: {exc}"
        )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="SmartPark AI is temporarily unavailable.",
        ) from exc
