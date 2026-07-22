from fastapi import APIRouter, Depends

from app.api.dependencies.auth import get_current_user
from app.schemas.user import UserResponse

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.get(
    "/me",
    response_model=UserResponse,
)
def get_me(
    current_user=Depends(get_current_user),
):
    """
    Retrieve the authenticated user.
    """

    return current_user