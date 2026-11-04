"""apnaSaathi API entry point.

Run from the backend folder:  uvicorn app.main:app --reload
Then open http://localhost:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.db.import_data import ensure_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_database()
    yield


app = FastAPI(
    title="apnaSaathi API",
    description="Digital acquisition and onboarding for small businesses (Accel Business, Project Udyam Digital). "
                "All data is synthetic; registry lookups are MOCK.",
    version="0.4.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
