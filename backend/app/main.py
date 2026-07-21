from fastapi import FastAPI

from app.api.router import router

app = FastAPI(
    title="SmartPark AI",
    description="Web-based Smart Parking Availability & Prediction System",
    version="1.0.0",
)


app.include_router(router)