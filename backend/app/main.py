"""
SmartPark AI Application Entry Point.

Creates and configures the FastAPI application,
registers exception handlers, and includes the
application API router.
"""

from fastapi import FastAPI

from app.api.router import router
from app.config import settings
from app.exceptions.handlers import register_exception_handlers


# ==========================================================
# FastAPI Application
# ==========================================================

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Web-based Smart Parking Availability "
        "& Prediction System"
    ),
)


# ==========================================================
# Exception Handlers
# ==========================================================

register_exception_handlers(
    app,
)


# ==========================================================
# API Router
# ==========================================================

app.include_router(
    router,
)