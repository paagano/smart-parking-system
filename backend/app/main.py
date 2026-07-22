from fastapi import FastAPI

from app.api.router import router
from app.config import settings
from app.exceptions.handlers import register_exception_handlers


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Web-based Smart Parking Availability & Prediction System",
)

register_exception_handlers(app)

app.include_router(router)