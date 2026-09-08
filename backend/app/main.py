"""
SmartPark AI Application Entry Point.

Creates and configures the FastAPI application,
registers middleware and exception handlers, and
includes the application API router.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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
# CORS - Cross-Origin Resource Sharing
# ==========================================================
#
# Allowed browser origins are loaded from the centralized
# BACKEND_CORS_ORIGINS setting in backend/.env.
#
# The environment variable is stored as a comma-separated
# string and converted into a list of origins here.
#
# Example:
#
# BACKEND_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,https://example.ngrok-free.app
#
# This keeps environment-specific hostnames out of the
# application source code.
# ==========================================================

cors_origins = [
    origin.strip()
    for origin in settings.FRONTEND_URLS.split(",")
    if origin.strip()
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================================
# Local Storage
# ==========================================================

app.mount(
    "/storage",
    StaticFiles(
        directory=settings.LOCAL_STORAGE_PATH,
    ),
    name="storage",
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