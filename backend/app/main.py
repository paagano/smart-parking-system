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
# CORS
# ==========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
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