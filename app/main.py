"""FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.config import PROJECT_ROOT
from app.db import close_db, init_db
from app.http_client import close_client
from app.sources import ofac

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("supplier-intelligence")

STATIC_DIR = PROJECT_ROOT / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Warm the OFAC index in the background so the first investigation is not
    # blocked on a multi-megabyte download.
    task = asyncio.create_task(_warm_ofac())
    yield
    task.cancel()
    await close_client()
    await close_db()


async def _warm_ofac() -> None:
    try:
        count = await ofac.ingest()
        log.info("OFAC ready: %d names indexed", count)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning("OFAC warm-up failed: %s", exc)


app = FastAPI(
    title="Supplier Intelligence API",
    version="0.1.0",
    description=(
        "AI-native third party risk investigation layer. Converts fragmented "
        "public information (OFAC, SEC EDGAR, GLEIF, GDELT, CourtListener) into "
        "a structured, evidence-backed intelligence object that an AI agent can "
        "consume."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"service": "Supplier Intelligence API", "docs": "/docs"}
