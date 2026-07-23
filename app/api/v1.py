"""Public API surface - the tool an AI agent actually calls."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app import db as database
from app.models import Investigation
from app.pipeline import investigate
from app.resolution.embeddings import active_backend
from app.schemas import InvestigationRequest, InvestigationResponse
from app.sources import ofac

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")


@router.post(
    "/supplier/investigate",
    response_model=InvestigationResponse,
    summary="Investigate a supplier and return an evidence-backed intelligence object",
)
async def investigate_supplier(request: InvestigationRequest) -> InvestigationResponse:
    try:
        result = await investigate(
            name=request.name,
            country=request.country,
            website=request.website,
            address=request.address,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("investigation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return InvestigationResponse(**result)


@router.get("/investigations", summary="List recent investigations")
async def list_investigations(limit: int = Query(20, ge=1, le=100)) -> dict:
    async with database.session_factory()() as session:
        rows = (
            await session.execute(
                select(Investigation).order_by(Investigation.id.desc()).limit(limit)
            )
        ).scalars().all()

    return {
        "count": len(rows),
        "investigations": [
            {
                "id": row.id,
                "name": row.query_name,
                "country": row.query_country,
                "risk_score": row.risk_score,
                "risk_level": row.risk_level,
                "duration_seconds": row.duration_seconds,
                "created_at": row.created_at,
            }
            for row in rows
        ],
    }


@router.get("/investigations/{investigation_id}", summary="Fetch a stored investigation")
async def get_investigation(investigation_id: int) -> dict:
    async with database.session_factory()() as session:
        row = await session.get(Investigation, investigation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="investigation not found")
    return row.result


@router.post("/admin/ofac/refresh", summary="Force a re-download of the OFAC SDN list")
async def refresh_ofac() -> dict:
    count = await ofac.ingest(force=True)
    return {"indexed_names": count}


@router.get("/health", summary="Service and dependency status")
async def health() -> dict:
    async with database.session_factory()() as session:
        investigations = (
            await session.execute(select(func.count(Investigation.id)))
        ).scalar_one()

    return {
        "status": "ok",
        "database": database.ACTIVE_BACKEND,
        "embedding_backend": active_backend(),
        "ofac_names_indexed": len(ofac._entries),  # noqa: SLF001 - diagnostic
        "investigations_stored": investigations,
    }
