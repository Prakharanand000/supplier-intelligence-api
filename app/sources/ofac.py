"""OFAC sanctions screening.

Pipeline:  OFAC SDN dataset -> normalize names -> searchable token index
           -> entity matching -> sanctions result

The full Specially Designated Nationals list (primary names + AKAs) is
downloaded, flattened one-row-per-name into PostgreSQL, and indexed in memory.
Screening never calls out to the network.
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from app.config import settings
from app.db import session_factory
from app.http_client import fetch
from app.models import OfacEntry, OfacMeta
from app.resolution.normalize import normalize_name
from app.resolution.similarity import name_similarity

log = logging.getLogger(__name__)

SDN_URLS = [
    "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV",
    "https://www.treasury.gov/ofac/downloads/sdn.csv",
]
ALT_URLS = [
    "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ALT.CSV",
    "https://www.treasury.gov/ofac/downloads/alt.csv",
]

# Screening thresholds. Below WEAK we report no match at all.
STRONG_MATCH = 0.90
WEAK_MATCH = 0.80

_index: dict[str, list[int]] = {}
_entries: list[dict] = []
_loaded = False
# Serializes ingestion: the startup warm-up and a screening-time self-heal can
# otherwise both download and bulk-write the list at the same time.
_ingest_lock = asyncio.Lock()


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip().strip('"').strip()
    return None if value in ("", "-0-") else value


async def _download(urls: list[str]) -> str | None:
    for url in urls:
        body = await fetch(url, ttl_hours=settings.ofac_refresh_hours, retries=2)
        if body and len(body) > 1000:
            log.info("OFAC: downloaded %s (%d bytes)", url, len(body))
            return body
    return None


def _parse_sdn(body: str) -> list[dict]:
    rows: list[dict] = []
    for row in csv.reader(io.StringIO(body)):
        if len(row) < 4:
            continue
        name = _clean(row[1])
        if not name:
            continue
        rows.append(
            {
                "ent_num": _clean(row[0]) or "",
                "name": name,
                "entity_type": _clean(row[2]),
                "program": _clean(row[3]),
                "remarks": _clean(row[11]) if len(row) > 11 else None,
                "is_alias": 0,
            }
        )
    return rows


def _parse_alt(body: str) -> list[dict]:
    rows: list[dict] = []
    for row in csv.reader(io.StringIO(body)):
        if len(row) < 4:
            continue
        name = _clean(row[3])
        if not name:
            continue
        rows.append(
            {
                "ent_num": _clean(row[0]) or "",
                "name": name,
                "entity_type": None,
                "program": None,
                "remarks": _clean(row[4]) if len(row) > 4 else None,
                "is_alias": 1,
            }
        )
    return rows


async def _needs_refresh() -> bool:
    async with session_factory()() as db:
        meta = (await db.execute(select(OfacMeta).limit(1))).scalar_one_or_none()
        if meta is None:
            return True
        count = (await db.execute(select(func.count(OfacEntry.id)))).scalar_one()
        if not count:
            return True
        refreshed = meta.refreshed_at
        if refreshed.tzinfo is None:
            refreshed = refreshed.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - refreshed
        return age > timedelta(hours=settings.ofac_refresh_hours)


async def ingest(force: bool = False) -> int:
    """Download and store the SDN list. Returns the number of names indexed."""
    async with _ingest_lock:
        return await _ingest_locked(force)


async def _ingest_locked(force: bool) -> int:
    global _loaded

    if not force and not await _needs_refresh():
        await _load_index()
        return len(_entries)

    sdn_body = await _download(SDN_URLS)
    if not sdn_body:
        log.error("OFAC: SDN download failed; screening will use any cached data")
        await _load_index()
        return len(_entries)

    records = _parse_sdn(sdn_body)
    alt_body = await _download(ALT_URLS)
    if alt_body:
        records += _parse_alt(alt_body)

    for rec in records:
        rec["normalized_name"] = normalize_name(rec["name"])

    async with session_factory()() as db:
        await db.execute(delete(OfacEntry))
        await db.execute(delete(OfacMeta))
        db.add_all([OfacEntry(**rec) for rec in records])
        db.add(
            OfacMeta(
                refreshed_at=datetime.now(timezone.utc),
                entry_count=len(records),
                source_url=SDN_URLS[0],
            )
        )
        await db.commit()

    log.info("OFAC: indexed %d names", len(records))
    _loaded = False
    await _load_index()
    return len(records)


async def _load_index() -> None:
    """Pull the stored list into memory and build a token -> rows index."""
    global _loaded, _entries, _index
    if _loaded:
        return

    async with session_factory()() as db:
        rows = (await db.execute(select(OfacEntry))).scalars().all()

    _entries = [
        {
            "ent_num": r.ent_num,
            "name": r.name,
            "normalized_name": r.normalized_name,
            "entity_type": r.entity_type,
            "program": r.program,
            "is_alias": r.is_alias,
            "remarks": r.remarks,
        }
        for r in rows
    ]

    _index = {}
    for i, entry in enumerate(_entries):
        for token in set(entry["normalized_name"].split()):
            _index.setdefault(token, []).append(i)

    _loaded = True
    log.info("OFAC: in-memory index ready (%d names)", len(_entries))


async def screen(name: str, country: str | None = None) -> dict:
    """Screen a company name against the SDN list.

    Returns the OFAC block of the investigation object.
    """
    await _load_index()

    # Self-heal: the startup warm-up can be skipped or CPU-throttled on
    # serverless hosts, so screening pulls the list itself rather than
    # silently reporting "no match" against an empty index.
    if not _entries:
        log.info("OFAC index empty at screening time - ingesting now")
        await ingest()

    normalized = normalize_name(name)
    if not normalized or not _entries:
        return {
            "match": False,
            "confidence": 0.0,
            "matched_entity": None,
            "source": "OFAC",
            "list_size": len(_entries),
            "note": "SDN list unavailable" if not _entries else "empty query name",
        }

    tokens = set(normalized.split())
    # Blocking: only score names sharing at least one token with the query.
    candidate_ids: set[int] = set()
    for token in tokens:
        candidate_ids.update(_index.get(token, []))

    best = None
    best_score = 0.0
    for idx in candidate_ids:
        entry = _entries[idx]
        score = name_similarity(normalized, entry["normalized_name"])["score"]
        if score > best_score:
            best_score, best = score, entry

    if best is None or best_score < WEAK_MATCH:
        return {
            "match": False,
            # Confidence that the *screening decision* is right, not that a
            # match exists: a clean name far from every SDN entry is a
            # confident clear.
            "confidence": round(min(0.99, 1.0 - best_score), 4) if best else 0.99,
            "matched_entity": None,
            "closest_entry": (
                {"name": best["name"], "similarity": round(best_score, 4)}
                if best
                else None
            ),
            "source": "OFAC",
            "list_size": len(_entries),
        }

    return {
        "match": True,
        "confidence": round(best_score, 4),
        "match_strength": "strong" if best_score >= STRONG_MATCH else "possible",
        "matched_entity": {
            "name": best["name"],
            "ent_num": best["ent_num"],
            "entity_type": best["entity_type"],
            "program": best["program"],
            "is_alias": bool(best["is_alias"]),
            "remarks": best["remarks"],
        },
        "source": "OFAC",
        "list_size": len(_entries),
    }
