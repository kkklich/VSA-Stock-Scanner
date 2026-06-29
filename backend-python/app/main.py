"""StockPilot API application entry point.

Run locally with:
    uvicorn app.main:app --reload --port 5111

The .NET backend listens on its own Kestrel port; this app defaults to 5111 so
the two can run side by side during the migration. Point the frontend's API base
URL at whichever backend you want to exercise.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import settings
from app.dependencies import create_http_client, set_http_client
from app.routers import stocks

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Open the shared stooq HTTP client on startup, close it on shutdown."""
    client = create_http_client()
    set_http_client(client)
    try:
        yield
    finally:
        set_http_client(None)
        await client.aclose()


app = FastAPI(
    title="StockPilot API",
    version=__version__,
    summary="VSA stock scanner for the Warsaw Stock Exchange (GPW).",
    lifespan=lifespan,
)

# CORS for the React frontend (Vite dev server defaults to 5173).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stocks.router)


@app.get("/health", tags=["meta"], summary="Liveness probe")
async def health() -> dict[str, str]:
    """Lightweight health check for load balancers and uptime monitors."""
    return {"status": "ok", "version": __version__}
