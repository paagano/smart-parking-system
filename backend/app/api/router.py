from fastapi import APIRouter

from app.api.endpoints.auth import router as auth_router
from app.api.endpoints.users import router as users_router
from app.api.endpoints.parking_facilities import (
    router as parking_facilities_router,
)
from app.api.endpoints.parking_zones import (
    router as parking_zones_router,
)
from app.api.endpoints.parking_bays import (
    router as parking_bays_router,
)

router = APIRouter()

# ==========================================================
# Authentication
# ==========================================================

router.include_router(auth_router)

# ==========================================================
# Users
# ==========================================================

router.include_router(users_router)

# ==========================================================
# Parking Facilities
# ==========================================================

router.include_router(parking_facilities_router)

# ==========================================================
# Parking Zones
# ==========================================================

router.include_router(parking_zones_router)

# ==========================================================
# Parking Bays
# ==========================================================

router.include_router(parking_bays_router)

# ==========================================================
# Root
# ==========================================================


@router.get("/")
async def root():
    """
    API health check endpoint.
    """

    return {
        "application": "SmartPark AI",
        "status": "healthy",
        "version": "1.0.0",
    }