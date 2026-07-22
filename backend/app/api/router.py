from fastapi import APIRouter

from app.api.endpoints.auth import router as auth_router
from app.api.endpoints.users import router as users_router

router = APIRouter()

router.include_router(auth_router)
router.include_router(users_router)


@router.get("/")
def root():
    return {
        "message": "Welcome to SmartPark AI 🚗",
        "status": "Running Successfully",
    }