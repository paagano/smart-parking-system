"""
Receipt API Endpoints.

REST API endpoints for SmartPark receipt management.

Responsibilities
----------------
- Retrieve a customer's receipts
- Retrieve a receipt by ID
- Retrieve a receipt by receipt number
- Publicly verify a receipt
- Generate a receipt PDF
- Regenerate a receipt PDF
- Download a receipt PDF
- Obtain a receipt PDF access URL

Business logic belongs in ReceiptService.
Persistence belongs in ReceiptRepository.
Storage operations belong in StorageService.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Response,
)

from app.api.dependencies.auth import (
    get_current_active_user,
)

from app.api.dependencies.receipts import (
    ReceiptServiceDep,
)

from app.exceptions.handlers import (
    NotFoundException,
)

from app.models.user import User

from app.schemas.receipt import (
    ReceiptListResponse,
    ReceiptLookupResponse,
    ReceiptResponse,
    ReceiptVerificationResponse,
)


# ==========================================================
# Router
# ==========================================================

router = APIRouter(
    prefix="/receipts",
    tags=["Receipts"],
)


# ==========================================================
# Get My Receipts
# ==========================================================


@router.get(
    "",
    response_model=ReceiptListResponse,
    summary="Get My Receipts",
)
async def get_my_receipts(
    service: ReceiptServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    limit: int = Query(
        default=100,
        ge=1,
        le=100,
        description="Maximum number of receipts to return.",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of receipts to skip.",
    ),
) -> ReceiptListResponse:
    """
    Retrieve receipts belonging to the authenticated user.
    """

    return await service.get_customer_receipts(
        customer_id=current_user.id,
        limit=limit,
        offset=offset,
    )


# ==========================================================
# Public Receipt Lookup
# ==========================================================


@router.get(
    "/lookup/{receipt_number}",
    response_model=ReceiptLookupResponse,
    summary="Public Receipt Lookup",
)
async def lookup_receipt(
    receipt_number: str,
    service: ReceiptServiceDep,
) -> ReceiptLookupResponse:
    """
    Retrieve public-facing receipt information.

    Sensitive information such as the verification token
    and internal storage details are excluded by
    ReceiptService.
    """

    return await service.lookup_receipt(
        receipt_number=receipt_number,
    )


# ==========================================================
# Verify Receipt
# ==========================================================


@router.get(
    "/verify/{receipt_number}",
    response_model=ReceiptVerificationResponse,
    summary="Verify Receipt",
)
async def verify_receipt(
    receipt_number: str,
    service: ReceiptServiceDep,
    verification_token: str = Query(
        ...,
        min_length=1,
        description="Receipt verification token.",
    ),
) -> ReceiptVerificationResponse:
    """
    Verify a receipt using its receipt number and
    verification token.

    This endpoint does not require authentication.

    The verification token is never returned in the
    verification response.
    """

    return await service.verify_receipt(
        receipt_number=receipt_number,
        verification_token=verification_token,
    )


# ==========================================================
# Get Receipt by ID
# ==========================================================


@router.get(
    "/{receipt_id}",
    response_model=ReceiptResponse,
    summary="Get Receipt",
)
async def get_receipt(
    receipt_id: int,
    service: ReceiptServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> ReceiptResponse:
    """
    Retrieve a receipt by ID.

    The receipt must belong to the authenticated user.
    """

    receipt = await service.get_receipt(
        receipt_id,
    )

    if receipt.customer_id != current_user.id:
        raise NotFoundException(
            "Receipt not found."
        )

    return receipt


# ==========================================================
# Get Receipt by Receipt Number
# ==========================================================


@router.get(
    "/number/{receipt_number}",
    response_model=ReceiptResponse,
    summary="Get Receipt by Receipt Number",
)
async def get_receipt_by_number(
    receipt_number: str,
    service: ReceiptServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> ReceiptResponse:
    """
    Retrieve a receipt using its public receipt number.

    The receipt must belong to the authenticated user.
    """

    receipt = await service.get_by_receipt_number(
        receipt_number,
    )

    if receipt.customer_id != current_user.id:
        raise NotFoundException(
            "Receipt not found."
        )

    return receipt


# ==========================================================
# Generate Receipt PDF
# ==========================================================


@router.post(
    "/{receipt_id}/generate",
    response_model=ReceiptResponse,
    summary="Generate Receipt PDF",
)
async def generate_receipt_pdf(
    receipt_id: int,
    service: ReceiptServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> ReceiptResponse:
    """
    Generate and store the PDF representation of a receipt.

    The receipt must belong to the authenticated user.

    If the receipt is already AVAILABLE, ReceiptService
    applies its idempotency rules.
    """

    receipt = await service.get_receipt(
        receipt_id,
    )

    if receipt.customer_id != current_user.id:
        raise NotFoundException(
            "Receipt not found."
        )

    return await service.generate_receipt(
        receipt_id=receipt_id,
    )


# ==========================================================
# Regenerate Receipt PDF
# ==========================================================


@router.post(
    "/{receipt_id}/regenerate",
    response_model=ReceiptResponse,
    summary="Regenerate Receipt PDF",
)
async def regenerate_receipt_pdf(
    receipt_id: int,
    service: ReceiptServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> ReceiptResponse:
    """
    Regenerate the stored PDF representation of a receipt.

    The financial snapshot, receipt identity and verification
    token remain unchanged.
    """

    receipt = await service.get_receipt(
        receipt_id,
    )

    if receipt.customer_id != current_user.id:
        raise NotFoundException(
            "Receipt not found."
        )

    return await service.regenerate_receipt(
        receipt_id=receipt_id,
    )


# ==========================================================
# Receipt PDF URL
# ==========================================================


@router.get(
    "/{receipt_id}/url",
    summary="Get Receipt PDF URL",
)
async def get_receipt_url(
    receipt_id: int,
    service: ReceiptServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    expires_in: int = Query(
        default=3600,
        ge=60,
        le=86400,
        description=(
            "Number of seconds for which the access URL "
            "should remain valid."
        ),
    ),
) -> dict[str, str]:
    """
    Generate an access URL for the receipt PDF.

    For private storage providers this may be a signed URL.
    """

    receipt = await service.get_receipt(
        receipt_id,
    )

    if receipt.customer_id != current_user.id:
        raise NotFoundException(
            "Receipt not found."
        )

    url = await service.get_receipt_url(
        receipt_id=receipt_id,
        expires_in=expires_in,
    )

    return {
        "receipt_number": receipt.receipt_number,
        "url": url,
    }


# ==========================================================
# Download Receipt PDF
# ==========================================================


@router.get(
    "/{receipt_id}/download",
    summary="Download Receipt PDF",
)
async def download_receipt_pdf(
    receipt_id: int,
    service: ReceiptServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> Response:
    """
    Download the generated receipt PDF.

    PDF bytes are retrieved through ReceiptService,
    which delegates storage operations to StorageService.
    """

    receipt = await service.get_receipt(
        receipt_id,
    )

    if receipt.customer_id != current_user.id:
        raise NotFoundException(
            "Receipt not found."
        )

    pdf_bytes = await service.download_receipt_pdf(
        receipt_id=receipt_id,
    )

    filename = f"{receipt.receipt_number}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            ),
        },
    )