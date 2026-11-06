"""apnaSaathi API entry point.

Run from the backend folder:  uvicorn app.main:app --reload
Then open http://localhost:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.api.advisor_routes import router as advisor_router
from app.api.channel_routes import router as channel_router
from app.api.kyc_routes import router as kyc_router
from app.api.ops_routes import router as ops_router
from app.api.quote_routes import router as quote_router
from app.api.routes import router
from app.db.import_data import ensure_database
from app.security import SecurityMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_database()
    yield


app = FastAPI(
    title="apnaSaathi API",
    description="Digital acquisition and onboarding for small businesses (Accel Business, Project Udyam Digital). "
                "All data is synthetic; registry lookups are MOCK.",
    version="0.9.0",
    lifespan=lifespan,
)
app.add_middleware(SecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(advisor_router)
app.include_router(quote_router)
app.include_router(kyc_router)
app.include_router(ops_router)
app.include_router(channel_router)

# Serve the built phone web app (frontend/dist) from the same server, if it has been built.
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="web")
