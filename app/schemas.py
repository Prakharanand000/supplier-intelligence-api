"""Pydantic request/response contracts for the public API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class InvestigationRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=400, examples=["Apple Inc."])
    country: str | None = Field(None, max_length=128, examples=["United States"])
    website: str | None = Field(None, max_length=512, examples=["https://apple.com"])
    address: str | None = Field(None, max_length=512)


class Supplier(BaseModel):
    name: str
    verified: bool
    status: str
    identity_confidence: float
    country: str | None = None
    website: str | None = None
    lei: str | None = None
    cik: str | None = None
    registration_number: str | None = None
    aliases: list[str] = []
    primary_source: str | None = None


class InvestigationResponse(BaseModel):
    investigation_id: int | None = None
    query: dict[str, Any]
    supplier: Supplier
    entity_resolution: dict[str, Any]
    ownership: list[dict[str, Any]]
    sanctions: dict[str, Any]
    adverse_media: list[dict[str, Any]]
    litigation: dict[str, Any]
    risk: dict[str, Any]
    evidence: list[dict[str, Any]]
    agent_summary: dict[str, Any]
    sources_consulted: dict[str, bool]
    optional_sources: dict[str, Any]
    duration_seconds: float
