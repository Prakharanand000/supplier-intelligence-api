"""Public API surface - the tool an AI agent actually calls."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app import crew
from app import db as database
from app import demo
from app import strategy
from app.models import Investigation
from app.pipeline import investigate
from app.agent.insight import connection_insight
from app.resolution.embeddings import active_backend
from app.risk.taxonomy import category_labels
from app.schemas import (
    GraphInsightRequest,
    InvestigationRequest,
    InvestigationResponse,
    StrategyRequest,
)
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
            city=request.city,
            entity_type=request.entity_type,
            date_of_birth=request.date_of_birth,
            registration_number=request.registration_number,
            aliases=request.aliases,
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


@router.get("/risk-categories", summary="Adverse-media risk taxonomy")
async def risk_categories() -> dict:
    """The five top-level categories the dashboard filters on."""
    return {"categories": category_labels()}


@router.post("/graph/insight", summary="AI insight for a graph connection or node")
async def graph_insight(request: GraphInsightRequest) -> dict:
    """Explain a specific network connection, grounded in the supplied facts."""
    return await connection_insight(request.model_dump())


@router.get("/crew/roster", summary="The multi-agent investigation crew")
async def crew_roster() -> dict:
    """Static definition of the ten specialist agents and their task order."""
    return {"agents": crew.roster()}


@router.post("/crew/trace", summary="Replay the crew against an investigation")
async def crew_trace(investigation: dict) -> dict:
    """Given a completed investigation object, return each specialist agent's
    real finding - the crew view's evidence-backed per-agent breakdown."""
    return crew.trace(investigation)


@router.get(
    "/crew/trace/{investigation_id}",
    summary="Replay the crew against a stored investigation",
)
async def crew_trace_stored(investigation_id: int) -> dict:
    async with database.session_factory()() as session:
        row = await session.get(Investigation, investigation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="investigation not found")
    return crew.trace(row.result)


@router.get("/strategy/samples", summary="Sample strategic decisions (offline)")
async def strategy_samples() -> dict:
    """Curated example decisions the board tab can render with no LLM key."""
    return {"samples": strategy.list_samples()}


@router.get("/strategy/sample/{sample_id}", summary="A full sample decision")
async def strategy_sample(sample_id: str) -> dict:
    from app.strategy.board import get_sample

    try:
        return get_sample(sample_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown sample") from None


@router.post("/strategy/decide", summary="Run the executive decision board")
async def strategy_decide(request: StrategyRequest) -> dict:
    """Evaluate one high-stakes question and return a board-ready verdict as a
    structured object (verdict, per-seat scores, ranked attacks, evidence audit,
    board vote). Runs live via Claude when a key is set, else serves a matching
    curated sample."""
    return await strategy.decide(request.question)


@router.get("/demo/subjects", summary="Demo subjects (offline sample dataset)")
async def demo_subjects() -> dict:
    """Fictional subjects with pre-built adverse media, for an instant demo."""
    return {"subjects": demo.list_subjects()}


@router.get("/demo/investigate/{subject_id}", summary="Assemble a demo investigation")
async def demo_investigate(subject_id: str) -> dict:
    try:
        return demo.build_investigation(subject_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown demo subject") from None


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
