from fastapi import FastAPI

from app.api.router import router
from app.config import settings


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Web-based Smart Parking Availability & Prediction System",
)

app.include_router(router)