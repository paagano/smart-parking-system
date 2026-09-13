"""
SmartPark operator ANPR endpoints.

The endpoint performs OCR only. Parking-session, reservation, and payment
workflows remain separate and authoritative in their existing services.
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.dependencies.auth import (
    require_attendant,
)
from app.services.anpr_service import ANPRService


router = APIRouter(
    prefix="/ai/anpr",
    tags=["ANPR"],
)


ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


@router.post(
    "/recognize",
    status_code=status.HTTP_200_OK,
    summary="Recognize a vehicle registration from a camera image",
)
async def recognize_vehicle_registration(
    attachment: UploadFile = File(...),
    _current_user=Depends(require_attendant),
) -> dict:
    """
    Recognize a Kenyan-style vehicle registration from an uploaded image.

    This endpoint intentionally has no side effects on SmartPark operational
    data. It does not create or modify sessions, reservations, bays, vehicles,
    payments, or database records.
    """

    content_type = (attachment.content_type or "").lower().strip()
    filename = (attachment.filename or "capture").strip()

    if content_type == "application/octet-stream":
        extension_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        suffix = (
            "." + filename.rsplit(".", 1)[-1].lower()
            if "." in filename
            else ""
        )
        content_type = extension_map.get(suffix, content_type)

    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="ANPR supports JPEG, PNG, and WebP camera images.",
        )

    image_bytes = await attachment.read(ANPRService.max_image_bytes + 1)

    try:
        result = await ANPRService.recognize(image_bytes)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        print(
            f"[SmartPark ANPR] OCR inference failed: "
            f"{type(exc).__name__}: {exc}"
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="ANPR recognition is temporarily unavailable.",
        ) from exc

    if result.registration is None:
        return {
            "recognized": False,
            "registration": None,
            "formatted_registration": None,
            "confidence": None,
            "variant": None,
            "candidates": result.candidates,
            "detections": result.detections,
        }

    return {
        "recognized": True,
        "registration": result.registration,
        "formatted_registration": result.formatted_registration,
        "confidence": round(result.confidence or 0.0, 4),
        "variant": result.variant,
        "candidates": result.candidates,
        "detections": result.detections,
    }
