"""Entity resolution engine.

Given a messy query ("ABC Manufacturing Ltd", "United States", "abc.com") and
a pile of candidate records scraped from independent registries, decide which
records refer to the same real-world company - and show the work.

Pipeline:  Raw entity -> Normalization -> Feature extraction -> Similarity
           -> Weighted confidence -> Match decision

Confidence is never hardcoded. Each feature contributes only when both sides
supply data for it, and the weights are renormalized over the features that
actually fired, so a match backed by name+website+ownership is scored on those
three rather than being diluted by fields nobody published.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.resolution import embeddings
from app.resolution.normalize import (
    name_tokens,
    normalize_address,
    normalize_country,
    normalize_domain,
    normalize_name,
)
from app.resolution.similarity import name_similarity

log = logging.getLogger(__name__)

# Relative importance of each signal. Renormalized per-comparison over the
# features that have data on both sides.
FEATURE_WEIGHTS = {
    "name": 0.40,
    "embedding": 0.20,
    "address": 0.15,
    "website": 0.15,
    "ownership": 0.10,
}

MATCH_THRESHOLD = 0.72
REVIEW_THRESHOLD = 0.55


@dataclass
class EntityRecord:
    """One candidate identity as published by a single source."""

    source: str
    name: str
    source_id: str | None = None
    aliases: list[str] = field(default_factory=list)
    country: str | None = None
    city: str | None = None
    address: str | None = None
    website: str | None = None
    officers: list[str] = field(default_factory=list)
    description: str | None = None
    url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def text_blob(self) -> str:
        """Text handed to the embedding model.

        Deliberately name/description only - geography is scored by the
        dedicated address feature, and including it here just adds noise that
        drags down the cosine for otherwise-identical names.
        """
        parts = [self.name, *self.aliases[:5]]
        if self.description:
            parts.append(self.description)
        return " | ".join(p for p in parts if p)


@dataclass
class ResolutionResult:
    record: EntityRecord
    confidence: float
    matched: bool
    breakdown: dict[str, float]
    weights_used: dict[str, float]
    explanation: str


def _best_name_score(query_name: str, record: EntityRecord) -> tuple[float, str]:
    """Score against the record's legal name and every alias; keep the best."""
    q = normalize_name(query_name)
    best_score, best_name = 0.0, record.name
    for candidate in [record.name, *record.aliases]:
        c = normalize_name(candidate)
        if not c:
            continue
        score = name_similarity(q, c)["score"]
        if score > best_score:
            best_score, best_name = score, candidate
    return best_score, best_name


def _address_score(
    query_country: str | None,
    query_address: str | None,
    record: EntityRecord,
) -> float | None:
    """Country match is the coarse signal; street text refines it."""
    qc = normalize_country(query_country)
    rc = normalize_country(record.country)
    country_score: float | None = None
    if qc and rc:
        country_score = 1.0 if qc == rc else 0.0

    qa = normalize_address(query_address)
    ra = normalize_address(record.address)
    street_score: float | None = None
    if qa and ra:
        qt, rt = set(qa.split()), set(ra.split())
        if qt and rt:
            street_score = len(qt & rt) / len(qt | rt)

    if country_score is not None and street_score is not None:
        return 0.5 * country_score + 0.5 * street_score
    if country_score is not None:
        return country_score
    return street_score


def _website_score(query_website: str | None, record: EntityRecord) -> float | None:
    qd = normalize_domain(query_website)
    rd = normalize_domain(record.website)
    if not qd or not rd:
        return None
    if qd == rd:
        return 1.0
    # example.com vs eu.example.com - same organisation, different subdomain.
    if qd.endswith("." + rd) or rd.endswith("." + qd):
        return 0.85
    q_core = qd.split(".")[0]
    r_core = rd.split(".")[0]
    return 0.6 if q_core and q_core == r_core else 0.0


def _ownership_score(
    corroborating_officers: list[str], record: EntityRecord
) -> float | None:
    """Shared executives are strong evidence two records are the same entity.

    `corroborating_officers` must come from the caller or from a *different*
    source than `record` - scoring a record against its own officer list would
    hand every candidate a free 1.0 and inflate every confidence equally.
    """
    if not corroborating_officers or not record.officers:
        return None
    q_sets = [name_tokens(o) for o in corroborating_officers if o]
    r_sets = [name_tokens(o) for o in record.officers if o]
    q_sets = [s for s in q_sets if s]
    r_sets = [s for s in r_sets if s]
    if not q_sets or not r_sets:
        return None

    hits = 0
    for qs in q_sets:
        for rs in r_sets:
            overlap = len(qs & rs) / max(1, min(len(qs), len(rs)))
            if overlap >= 0.5:
                hits += 1
                break
    return min(1.0, hits / min(len(q_sets), len(r_sets)))


async def resolve(
    *,
    query_name: str,
    candidates: list[EntityRecord],
    query_country: str | None = None,
    query_website: str | None = None,
    query_address: str | None = None,
    query_officers: list[str] | None = None,
) -> list[ResolutionResult]:
    """Score every candidate against the query, best first."""
    if not candidates:
        return []

    query_officers = query_officers or []

    # One batched embedding call for the query plus all candidate blobs.
    blobs = [query_name.strip()] + [c.text_blob() for c in candidates]
    try:
        vectors = await embeddings.embed(blobs)
        query_vec, candidate_vecs = vectors[0], vectors[1:]
    except Exception as exc:  # noqa: BLE001 - embeddings are an enhancement
        log.warning("Embedding step failed, continuing without it: %s", exc)
        query_vec, candidate_vecs = [], [[] for _ in candidates]

    results: list[ResolutionResult] = []
    for record, vec in zip(candidates, candidate_vecs):
        name_score, matched_name = _best_name_score(query_name, record)
        # Officers named by the caller, plus officers published by any *other*
        # source. Excluding the record's own source keeps this an independent
        # corroboration signal rather than a self-confirming one.
        corroborating = list(query_officers) + [
            officer
            for other in candidates
            if other.source != record.source
            for officer in other.officers
        ]
        features: dict[str, float | None] = {
            "name": name_score,
            "embedding": embeddings.cosine(query_vec, vec) if query_vec and vec else None,
            "address": _address_score(query_country, query_address, record),
            "website": _website_score(query_website, record),
            "ownership": _ownership_score(corroborating, record),
        }

        active = {k: v for k, v in features.items() if v is not None}
        total_weight = sum(FEATURE_WEIGHTS[k] for k in active) or 1.0
        weights = {k: FEATURE_WEIGHTS[k] / total_weight for k in active}
        confidence = sum(active[k] * weights[k] for k in active)

        breakdown = {k: round(v, 4) for k, v in active.items()}
        explanation = _explain(matched_name, record, breakdown, weights)

        results.append(
            ResolutionResult(
                record=record,
                confidence=round(confidence, 4),
                matched=confidence >= MATCH_THRESHOLD,
                breakdown=breakdown,
                weights_used={k: round(w, 3) for k, w in weights.items()},
                explanation=explanation,
            )
        )

    results.sort(key=lambda r: r.confidence, reverse=True)
    return results


def _explain(
    matched_name: str,
    record: EntityRecord,
    breakdown: dict[str, float],
    weights: dict[str, float],
) -> str:
    ordered = sorted(breakdown.items(), key=lambda kv: weights[kv[0]], reverse=True)
    parts = [f"{k} {v:.2f} (w={weights[k]:.2f})" for k, v in ordered]
    return (
        f"{record.source} record '{matched_name}' scored on: " + ", ".join(parts)
    )


def pick_best(results: list[ResolutionResult]) -> ResolutionResult | None:
    return results[0] if results else None


def verdict(confidence: float) -> str:
    if confidence >= MATCH_THRESHOLD:
        return "verified"
    if confidence >= REVIEW_THRESHOLD:
        return "probable"
    return "unverified"
