"""
SmartPark AI Endpoints

API endpoints for the SmartPark AI assistant.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from io import BytesIO

import httpx
from openai import AsyncOpenAI
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Response, status
from pydantic import BaseModel, Field

from app.api.dependencies.auth import (
    get_current_active_user,
)
from app.api.dependencies.services import (
    SmartParkChatServiceDep,
)

from app.config.settings import settings
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
# Realtime Voice Schemas
# ==========================================================


class AIRealtimeToolRequest(BaseModel):
    """
    Execute a SmartPark tool requested by an authenticated
    Realtime voice session.

    The tool itself is selected by OpenAI. The authenticated
    customer identity is always taken from the backend user
    dependency and is never accepted from this request.
    """

    tool_name: str = Field(..., min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


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


# ==========================================================
# Realtime Voice Document Upload
# ==========================================================


@router.post(
    "/realtime/file",
    status_code=status.HTTP_200_OK,
    summary="Upload and analyze a document for an active SmartPark Realtime conversation",
)
async def upload_realtime_file(
    current_user: CurrentUserDep,
    attachment: UploadFile = File(...),
) -> dict[str, str]:
    """
    Upload a document to OpenAI Files, analyze it through the Responses API,
    and return a concise factual briefing to the browser.

    The browser then injects that briefing as input_text into the already
    established Realtime conversation. The live WebRTC session is therefore
    not interrupted and the OpenAI API key never reaches the browser.
    """

    allowed_content_types = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "text/plain",
        "text/csv",
        "application/json",
        "image/jpeg",
        "image/png",
        "image/webp",
    }

    content_type = (attachment.content_type or "").lower().strip()
    filename = (attachment.filename or "document").strip()

    # Some browsers/proxies occasionally send application/octet-stream for a
    # known extension. Normalize those common cases rather than rejecting a
    # valid receipt/document unnecessarily.
    if content_type == "application/octet-stream":
        extension_map = {
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xls": "application/vnd.ms-excel",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".ppt": "application/vnd.ms-powerpoint",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".txt": "text/plain",
            ".csv": "text/csv",
            ".json": "application/json",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        content_type = extension_map.get(suffix, content_type)

    if content_type not in allowed_content_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                "Unsupported document type. Please upload a PDF, Word, Excel, "
                "PowerPoint, text, CSV, JSON, JPEG, PNG, or WebP file."
            ),
        )

    max_attachment_bytes = 10 * 1024 * 1024
    attachment_bytes = await attachment.read(max_attachment_bytes + 1)

    if not attachment_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The selected document is empty.",
        )

    if len(attachment_bytes) > max_attachment_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Document attachments must not exceed 10 MB.",
        )

    openai_client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=90.0,
    )

    file_id: str | None = None

    try:
        # Use the official OpenAI SDK here rather than manually constructing
        # the multipart request. This avoids multipart encoding differences
        # between httpx and the current Files API contract.
        uploaded_file = await openai_client.files.create(
            file=(filename, BytesIO(attachment_bytes), content_type),
            purpose="user_data",
        )
        file_id = uploaded_file.id

        print(
            "[SmartPark AI] Realtime document uploaded to OpenAI "
            f"| customer_id={current_user.id} "
            f"| filename={filename} "
            f"| file_id={file_id}"
        )

        analysis_prompt = (
            "Review the attached document for a SmartPark AI voice assistant. "
            "Extract the important factual information contained in the document. "
            "Preserve names, dates, amounts, reference numbers, statuses, and "
            "other exact values. Be concise, do not invent facts, and clearly "
            "state when information is missing or unclear. Return a factual "
            "document briefing suitable for another assistant to use in answering "
            "the user's question."
        )

        # File inputs are supported by the Responses API. The Realtime data
        # channel itself will receive only input_text; it does not receive an
        # input_file item directly.
        response = await openai_client.responses.create(
            model=settings.OPENAI_MODEL,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": analysis_prompt,
                        },
                        {
                            "type": "input_file",
                            "file_id": file_id,
                        },
                    ],
                }
            ],
        )

        document_context = (getattr(response, "output_text", None) or "").strip()

        if not document_context:
            print(
                "[SmartPark AI] Realtime document analysis returned no output "
                f"| file_id={file_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="SmartPark could not extract usable information from the document.",
            )

        print(
            "[SmartPark AI] Realtime document analyzed successfully "
            f"| customer_id={current_user.id} "
            f"| filename={filename} "
            f"| file_id={file_id}"
        )

        return {
            "file_id": file_id,
            "filename": filename,
            "document_context": document_context,
        }

    except HTTPException:
        raise
    except Exception as exc:
        print(
            "[SmartPark AI] Realtime document upload/analysis failed: "
            f"{type(exc).__name__}: {exc}"
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "SmartPark could not process the attached document. "
                "Please try again with a PDF or image receipt."
            ),
        ) from exc
    finally:
        # These uploaded files are only needed long enough to analyze the
        # current attachment. Delete them after processing to avoid accumulating
        # user documents in the OpenAI project.
        if file_id:
            try:
                await openai_client.files.delete(file_id)
            except Exception as cleanup_exc:
                print(
                    "[SmartPark AI] Realtime document cleanup failed: "
                    f"file_id={file_id} "
                    f"error={type(cleanup_exc).__name__}: {cleanup_exc}"
                )



# ==========================================================
# Realtime Voice Session
# ==========================================================


@router.post(
    "/realtime/session",
    status_code=status.HTTP_201_CREATED,
    response_class=Response,
    summary="Create an authenticated SmartPark Realtime voice session",
)
async def create_realtime_voice_session(
    chat_service: SmartParkChatServiceDep,
    current_user: CurrentUserDep,
    sdp: str = Form(...),
    latitude: float | None = Form(default=None),
    longitude: float | None = Form(default=None),
) -> Response:
    """
    Create a WebRTC Realtime voice call with OpenAI.

    The browser sends only its WebRTC SDP offer. The OpenAI API key
    remains server-side. SmartPark's Realtime session configuration,
    trusted tools, and voice instructions are provided by the existing
    SmartParkChatService.

    This endpoint does not alter the existing /ai/chat or
    /ai/chat/attachment contracts.
    """

    outbound_sdp = sdp

    print(
        "[SmartPark AI] Realtime SDP offer received "
        f"| length={len(outbound_sdp)} "
        f"| trailing_crlf={outbound_sdp.endswith(chr(13) + chr(10))}"
    )

    if not outbound_sdp.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A valid WebRTC SDP offer is required.",
        )

    session_config = chat_service.get_realtime_session_config(
        latitude=latitude,
        longitude=longitude,
    )

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0)
        ) as client:
            openai_response = await client.post(
                "https://api.openai.com/v1/realtime/calls",
                headers={
                    "Authorization": (
                        f"Bearer {settings.OPENAI_API_KEY}"
                    ),
                    "Accept": "application/sdp",
                },
                files={
                    "sdp": (
                        None,
                        outbound_sdp.encode("utf-8"),
                        "application/sdp",
                    ),
                    "session": (
                        None,
                        json.dumps(session_config).encode("utf-8"),
                        "application/json",
                    ),
                },
            )

        if openai_response.status_code >= 400:
            print(
                "[SmartPark AI] Realtime session creation failed: "
                f"status={openai_response.status_code} "
                f"body={openai_response.text[:1000]}"
            )

            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="SmartPark realtime voice is temporarily unavailable.",
            )

        answer_sdp = openai_response.text

        if not answer_sdp:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="OpenAI returned an empty realtime SDP answer.",
            )

        print(
            "[SmartPark AI] Realtime voice session created "
            f"| customer_id={current_user.id}"
        )

        return Response(
            content=answer_sdp,
            media_type="application/sdp",
            status_code=status.HTTP_201_CREATED,
        )

    except HTTPException:
        raise
    except Exception as exc:
        print(
            "[SmartPark AI] Realtime session request failed: "
            f"{type(exc).__name__}: {exc}"
        )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="SmartPark realtime voice is temporarily unavailable.",
        ) from exc


# ==========================================================
# Realtime SmartPark Tool Execution
# ==========================================================


@router.post(
    "/realtime/tool",
    status_code=status.HTTP_200_OK,
    summary="Execute a SmartPark tool for a Realtime voice session",
)
async def execute_realtime_tool(
    data: AIRealtimeToolRequest,
    chat_service: SmartParkChatServiceDep,
    current_user: CurrentUserDep,
) -> dict[str, Any]:
    """
    Execute a function requested by the authenticated Realtime
    SmartPark voice session.

    The browser may send the tool name and model-generated arguments,
    but the authenticated customer identity always comes from
    current_user.

    Actual SmartPark business logic is delegated to the existing
    SmartParkChatService Realtime tool executor.
    """

    try:
        result = await chat_service.execute_realtime_tool(
            tool_name=data.tool_name,
            arguments=data.arguments,
            customer_id=current_user.id,
            latitude=data.latitude,
            longitude=data.longitude,
        )

        return {
            "tool_name": data.tool_name,
            "output": result,
        }

    except Exception as exc:
        print(
            "[SmartPark AI] Realtime tool execution failed: "
            f"{data.tool_name} | "
            f"{type(exc).__name__}: {exc}"
        )

        return {
            "tool_name": data.tool_name,
            "output": {
                "error": (
                    "The requested SmartPark operation "
                    "could not be completed."
                ),
                "operation": data.tool_name,
            },
        }

