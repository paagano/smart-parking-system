from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies.auth import require_admin
from app.api.dependencies.services import AuthServiceDep
from app.models.user import User
from app.schemas.user import (
    AdminAttendantCreate,
    AttendantFacilityUpdate,
    UserResponse,
)

router = APIRouter(
    prefix="/admin/operators",
    tags=["Administration - Operators"],
)


@router.get("", response_model=list[UserResponse])
async def list_operators(
    _: Annotated[User, Depends(require_admin)],
    auth_service: AuthServiceDep,
):
    return await auth_service.list_attendants()


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_operator(
    data: AdminAttendantCreate,
    _: Annotated[User, Depends(require_admin)],
    auth_service: AuthServiceDep,
):
    try:
        return await auth_service.create_attendant(data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.patch(
    "/{user_id}/facility",
    response_model=UserResponse,
)
async def assign_operator_facility(
    user_id: int,
    data: AttendantFacilityUpdate,
    _: Annotated[User, Depends(require_admin)],
    auth_service: AuthServiceDep,
):
    try:
        return await auth_service.assign_attendant_facility(
            user_id=user_id,
            data=data,
        )
    except ValueError as exc:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(exc).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=status_code,
            detail=str(exc),
        ) from exc
