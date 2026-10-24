"""Entry point of the API: run it with `uvicorn app.main:app --reload`"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import select

from app.auth import create_first_admin
from app.config import settings
from app.database import SessionDep, create_db_and_tables
from app.routers import rooms, users

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once when the API starts: create the tables and the first admin"""
    create_db_and_tables()
    create_first_admin()
    yield


app = FastAPI(
    title="Workspace Booking API",
    description="Book meeting rooms without double bookings.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add how long the request took (in seconds) as a response header"""
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{time.perf_counter() - start:.4f}"
    return response


app.include_router(users.router, prefix="/api/v1")
app.include_router(rooms.router, prefix="/api/v1")


@app.get("/health", tags=["health"])
def health(session: SessionDep) -> dict[str, str]:
    """Check that the API is running and the database answers"""
    session.exec(select(1))
    return {"status": "ok"}
