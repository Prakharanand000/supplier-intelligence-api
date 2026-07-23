"""Supplier investigation engine - orchestrates the whole run.

    live sources (concurrent)
        -> entity resolution
        -> evidence layer
        -> risk signals
        -> Claude reasoning
        -> structured intelligence object
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from sqlalchemy import select

from app.agent import generate_report
from app.config import settings
from app.db import session_factory
from app.models import Company, Document, Investigation, Person, Relationship, RiskSignal
from app.resolution import EntityRecord, pick_best, resolve, verdict
from app.resolution.embeddings import active_backend
from app.resolution.normalize import normalize_domain, normalize_name
from app.risk import evaluate, recommendation
from app.sources import courtlistener, gdelt, gleif, ofac, optional_sources, sec

log = logging.getLogger(__name__)


async def _safe(name: str, coro, default):
    """Run a source, never let it take the investigation down with it."""
    try:
        return name, await coro, True
    except Exception as exc:  # noqa: BLE001
        log.warning("source %s failed: %s", name, exc)
        return name, default, False


async def investigate(
    *,
    name: str,
    country: str | None = None,
    website: str | None = None,
    address: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()

    # ---- 1. Live source fan-out ------------------------------------------
    tasks = [
        _safe("sec", sec.search(name, country), []),
        _safe("gleif", gleif.search(name, country), []),
        _safe("gdelt", gdelt.search(name), []),
        _safe("courtlistener", courtlistener.search(name),
              {"available": False, "cases": [], "note": "not run"}),
        _safe("ofac", ofac.screen(name, country),
              {"match": False, "confidence": 0.0, "matched_entity": None,
               "source": "OFAC", "list_size": 0}),
    ]

    # Keep whatever finished inside the budget rather than discarding the whole
    # run: a report backed by three sources beats no report at all, and the
    # sources that missed are reported as coverage gaps.
    pending = [asyncio.ensure_future(task) for task in tasks]
    done, still_running = await asyncio.wait(
        pending, timeout=settings.investigation_timeout_seconds
    )
    for task in still_running:
        task.cancel()
    if still_running:
        log.warning(
            "investigation for %r hit the %ss budget; %d source(s) cancelled",
            name, settings.investigation_timeout_seconds, len(still_running),
        )

    results: dict[str, Any] = {}
    consulted: dict[str, bool] = {
        k: False for k in ("sec", "gleif", "gdelt", "courtlistener", "ofac")
    }
    for task in done:
        try:
            source_name, payload, ok = task.result()
        except Exception as exc:  # noqa: BLE001
            log.warning("source task raised: %s", exc)
            continue
        results[source_name] = payload
        consulted[source_name] = ok

    sec_records: list[EntityRecord] = results.get("sec") or []
    gleif_records: list[EntityRecord] = results.get("gleif") or []
    media: list[dict] = results.get("gdelt") or []
    litigation: dict = results.get("courtlistener") or {
        "available": False, "cases": [], "note": "not run"
    }
    sanctions: dict = results.get("ofac") or {
        "match": False, "confidence": 0.0, "matched_entity": None,
        "source": "OFAC", "list_size": 0,
    }
    # An empty candidate list from a source that ran is a legitimate result,
    # but a source that raised was never really consulted.
    consulted["ofac"] = consulted["ofac"] and bool(sanctions.get("list_size"))

    # ---- 2. Entity resolution --------------------------------------------
    candidates = sec_records + gleif_records

    # No officers are supplied by the caller; the engine derives its own
    # cross-source corroboration from the candidate set.
    resolutions = await resolve(
        query_name=name,
        candidates=candidates,
        query_country=country,
        query_website=website,
        query_address=address,
    )
    best = pick_best(resolutions)
    identity_confidence = best.confidence if best else 0.0
    identity_verdict = verdict(identity_confidence)

    supplier = _build_supplier(
        name, country, website, best, resolutions, identity_confidence, identity_verdict
    )

    # ---- 3. Re-screen against the resolved legal name ---------------------
    if best and normalize_name(best.record.name) != normalize_name(name):
        try:
            rescreen = await ofac.screen(best.record.name, country)
            if rescreen.get("match") and not sanctions.get("match"):
                rescreen["screened_name"] = best.record.name
                sanctions = rescreen
        except Exception as exc:  # noqa: BLE001
            log.warning("OFAC re-screen failed: %s", exc)

    # ---- 4. Ownership graph ----------------------------------------------
    ownership = _build_ownership(resolutions)

    # ---- 5. Evidence layer -----------------------------------------------
    evidence = _build_evidence(resolutions, media, litigation, sanctions)

    # ---- 6. Risk signals --------------------------------------------------
    risk, signals = evaluate(
        sanctions=sanctions,
        litigation=litigation,
        adverse_media=media,
        identity_confidence=identity_confidence,
        identity_verdict=identity_verdict,
        ownership=ownership,
        sources_consulted=consulted,
    )

    investigation: dict[str, Any] = {
        "query": {
            "name": name,
            "country": country,
            "website": website,
            "address": address,
        },
        "supplier": supplier,
        "entity_resolution": {
            "embedding_backend": active_backend(),
            "candidates_considered": len(candidates),
            "match_threshold": 0.72,
            "selected": (
                {
                    "source": best.record.source,
                    "name": best.record.name,
                    "confidence": best.confidence,
                    "confidence_breakdown": best.breakdown,
                    "weights_used": best.weights_used,
                    "explanation": best.explanation,
                }
                if best
                else None
            ),
            "alternatives": [
                {
                    "source": r.record.source,
                    "name": r.record.name,
                    "confidence": r.confidence,
                    "confidence_breakdown": r.breakdown,
                    "explanation": r.explanation,
                }
                for r in resolutions[1:6]
            ],
        },
        "ownership": ownership,
        "sanctions": sanctions,
        "adverse_media": media,
        "litigation": litigation,
        "risk": risk,
        "evidence": evidence,
        "sources_consulted": consulted,
        "optional_sources": {
            "opencorporates": optional_sources.opencorporates(name, country),
            "virustotal": optional_sources.virustotal(website),
        },
        "_recommendation": recommendation(risk),
    }

    # ---- 7. Claude reasoning layer ---------------------------------------
    report = await generate_report(investigation)
    report.setdefault("recommendation", investigation["_recommendation"])
    report["rule_based_recommendation"] = investigation.pop("_recommendation")
    investigation["agent_summary"] = report

    investigation["duration_seconds"] = round(time.perf_counter() - started, 2)

    # ---- 8. Persist -------------------------------------------------------
    try:
        investigation["investigation_id"] = await _persist(
            investigation, ownership, signals, evidence
        )
    except Exception as exc:  # noqa: BLE001 - a storage failure must not lose the result
        log.warning("persistence failed: %s", exc)
        investigation["investigation_id"] = None

    return investigation


# --------------------------------------------------------------------------
# Assembly helpers
# --------------------------------------------------------------------------
def _build_supplier(
    name: str,
    country: str | None,
    website: str | None,
    best,
    resolutions: list,
    confidence: float,
    status: str,
) -> dict[str, Any]:
    lei = next(
        (r.record.raw.get("lei") for r in resolutions
         if r.record.source == "GLEIF" and r.confidence >= 0.6),
        None,
    )
    cik = next(
        (r.record.raw.get("cik") for r in resolutions
         if r.record.source == "SEC" and r.confidence >= 0.6),
        None,
    )
    registered_as = next(
        (r.record.raw.get("registered_as") for r in resolutions
         if r.record.source == "GLEIF" and r.confidence >= 0.6),
        None,
    )

    if best:
        record = best.record
        return {
            "name": record.name,
            "verified": status == "verified",
            "status": status,
            "identity_confidence": confidence,
            "country": record.country or country,
            "website": record.website or (normalize_domain(website) or None),
            "lei": lei,
            "cik": cik,
            "registration_number": registered_as or (cik and f"CIK:{cik}"),
            "aliases": record.aliases[:10],
            "primary_source": record.source,
        }

    return {
        "name": name,
        "verified": False,
        "status": status,
        "identity_confidence": confidence,
        "country": country,
        "website": normalize_domain(website) or None,
        "lei": None,
        "cik": None,
        "registration_number": None,
        "aliases": [],
        "primary_source": None,
    }


def _build_ownership(resolutions: list) -> list[dict[str, Any]]:
    """Related parties belonging to the *resolved* entity only.

    Officers are attributed strictly to records that resolved to this supplier:
    the selected record, plus any other record that cleared the match
    threshold. Pooling every near-miss candidate would attribute a rejected
    lookalike's board to the supplier under investigation.
    """
    if not resolutions:
        return []

    contributing = [resolutions[0]] + [
        res for res in resolutions[1:] if res.matched
    ]

    ownership: list[dict[str, Any]] = []
    seen: set[str] = set()

    for res in contributing:
        record = res.record

        for officer in record.raw.get("officers", []) or []:
            key = normalize_name(officer["name"])
            if not key or key in seen:
                continue
            seen.add(key)
            ownership.append(
                {
                    "name": officer["name"],
                    "role": officer.get("role") or "Section 16 insider",
                    "relationship_type": "officer_or_director",
                    "country": record.country,
                    "source": record.source,
                    "evidence_url": officer.get("source_url") or record.url,
                    # More Form 4 filings = stronger evidence of an ongoing role.
                    "confidence": round(
                        min(0.95, 0.6 + 0.05 * officer.get("filings", 1)) * res.confidence,
                        4,
                    ),
                }
            )

        for parent in record.raw.get("parents", []) or []:
            key = normalize_name(parent["name"])
            if not key or key in seen:
                continue
            seen.add(key)
            ownership.append(
                {
                    "name": parent["name"],
                    "role": parent["relationship"].replace("_", " ").title(),
                    "relationship_type": parent["relationship"],
                    "country": parent.get("jurisdiction"),
                    "lei": parent.get("lei"),
                    "source": "GLEIF",
                    "evidence_url": (
                        f"https://search.gleif.org/#/record/{parent.get('lei')}"
                        if parent.get("lei")
                        else None
                    ),
                    "confidence": round(0.92 * res.confidence, 4),
                }
            )

    ownership.sort(key=lambda o: o["confidence"], reverse=True)
    return ownership


def _build_evidence(
    resolutions: list,
    media: list[dict],
    litigation: dict,
    sanctions: dict,
) -> list[dict[str, Any]]:
    """Flat, citable evidence array. Every report claim points back into this."""
    evidence: list[dict[str, Any]] = []

    def add(source: str, description: str, url: str | None, extra: dict | None = None):
        evidence.append(
            {
                "id": f"E{len(evidence) + 1}",
                "source": source,
                "url": url,
                "description": description,
                **(extra or {}),
            }
        )

    for res in resolutions[:6]:
        record = res.record
        add(
            record.source,
            f"{record.source} registry record for '{record.name}'"
            + (f" ({record.country})" if record.country else "")
            + f"; resolution confidence {res.confidence:.2f}",
            record.url,
            {"resolution_confidence": res.confidence},
        )
        for filing in (record.raw.get("recent_filings") or [])[:3]:
            add(
                "SEC",
                f"Filing {filing['form']} dated {filing['filed']}"
                + (f": {filing['description']}" if filing.get("description") else ""),
                filing.get("url"),
                {"date": filing["filed"]},
            )

    add(
        "OFAC",
        (
            f"Sanctions screening against the SDN list "
            f"({sanctions.get('list_size', 0)} names): "
            + ("MATCH " + str((sanctions.get("matched_entity") or {}).get("name"))
               if sanctions.get("match")
               else "no match")
        ),
        "https://ofac.treasury.gov/sanctions-list-service",
        {"match": bool(sanctions.get("match"))},
    )

    for case in (litigation.get("cases") or [])[:6]:
        add(
            "CourtListener",
            f"{case['case']} ({case.get('court') or 'unknown court'}, "
            f"filed {case.get('date') or 'date unknown'})",
            case.get("url"),
            {"date": case.get("date"), "confidence": case.get("confidence")},
        )

    for article in media[:8]:
        add(
            "GDELT",
            f"{article['title']} - {article['source']}",
            article.get("url"),
            {
                "date": article.get("date"),
                "sentiment": article["sentiment"],
                "severity": article["severity"],
                "confidence": article["confidence"],
            },
        )

    return evidence


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------
async def _persist(
    investigation: dict, ownership: list[dict], signals: list, evidence: list[dict]
) -> int:
    supplier = investigation["supplier"]

    async with session_factory()() as db:
        normalized = normalize_name(supplier["name"])
        company = (
            await db.execute(
                select(Company).where(Company.normalized_name == normalized)
            )
        ).scalars().first()

        if company is None:
            company = Company(
                legal_name=supplier["name"], normalized_name=normalized
            )
            db.add(company)

        company.aliases = supplier["aliases"]
        company.country = supplier["country"]
        company.website = supplier["website"]
        company.lei_number = supplier["lei"]
        company.cik = supplier["cik"]
        company.registration_number = supplier["registration_number"]
        company.identity_confidence = supplier["identity_confidence"]
        await db.flush()

        for owner in ownership:
            db.add(
                Person(
                    name=owner["name"],
                    role=owner.get("role"),
                    country=owner.get("country"),
                    confidence=owner.get("confidence"),
                    source=owner.get("source"),
                    company_id=company.id,
                )
            )
            db.add(
                Relationship(
                    source_entity=owner["name"],
                    target_entity=company.legal_name,
                    relationship_type=owner["relationship_type"],
                    confidence=owner.get("confidence", 0.0),
                    evidence_source=owner.get("source"),
                )
            )

        for item in evidence:
            db.add(
                Document(
                    company_id=company.id,
                    source=item["source"],
                    title=item["description"][:2000],
                    url=item.get("url"),
                    published_date=item.get("date"),
                    doc_metadata={
                        k: v for k, v in item.items()
                        if k not in ("id", "source", "url", "description")
                    },
                )
            )

        for signal in signals:
            db.add(
                RiskSignal(
                    company_id=company.id,
                    category=signal.category,
                    description=signal.description,
                    severity=signal.severity,
                    source=signal.source,
                    confidence=signal.confidence,
                )
            )

        record = Investigation(
            query_name=investigation["query"]["name"],
            query_country=investigation["query"]["country"],
            query_website=investigation["query"]["website"],
            company_id=company.id,
            risk_score=investigation["risk"]["score"],
            risk_level=investigation["risk"]["level"],
            duration_seconds=investigation["duration_seconds"],
            result=investigation,
        )
        db.add(record)
        await db.commit()
        return record.id
