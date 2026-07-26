"""The multi-agent crew, merged into this app.

The original CrewAI project ("FinalSupplierThirdPartyRiskIntelligence") runs a
sequential crew of ten specialist agents over live web tools. This module ports
that crew into the app: it keeps the agents' identities (role, goal, tools,
task order and dependencies) and re-grounds every specialist on the app's own
live sources and deterministic engines instead of an LLM+search loop.

`ROSTER` is the static definition rendered by the "Agent crew" view.
`trace(investigation)` replays the crew against a completed investigation and
returns, per agent, what it actually found - so the crew view is backed by real
evidence rather than a canned animation.
"""

from __future__ import annotations

from typing import Any

# The e-mail the crew's alerting agent escalates HIGH/CRITICAL findings to,
# mirroring the original crew's distribute_report_alert task.
ALERT_RECIPIENT = "prakharanandus000@gmail.com"

# ---------------------------------------------------------------------------
# Static crew definition
# ---------------------------------------------------------------------------
# Each entry keeps the original CrewAI agent identity and adds `live_sources`:
# the source(s)/engine in *this* app that now powers the specialist. `order` is
# the sequential task order; `context` lists the tasks it depends on, exactly as
# the crew's tasks.yaml declared them.
ROSTER: list[dict[str, Any]] = [
    {
        "id": "lead_investigator",
        "order": 0,
        "role": "Lead Compliance & FinCrime Investigator",
        "task": "Orchestrate the investigation",
        "goal": (
            "Dispatch each specialist, track which sources succeeded or failed, "
            "and compile every output for risk synthesis. A failed source is "
            "logged as a coverage gap - the investigation never halts."
        ),
        "backstory": (
            "15+ years across FATF-member regulators and Tier-1 bank compliance. "
            "Rigorous source tracking, airtight coverage-gap documentation."
        ),
        "crew_tools": [],
        "live_sources": ["Pipeline orchestrator"],
        "model": "gpt-4o-mini",
        "icon": "compass",
        "context": [],
    },
    {
        "id": "entity_name_variant_specialist",
        "order": 1,
        "role": "Entity Name Variant Specialist",
        "task": "Generate name aliases",
        "goal": (
            "Before screening, expand the subject into every likely name variant "
            "- abbreviations, acronyms, transliterations, former names, DBAs and "
            "jurisdiction suffixes - to maximise downstream match recall."
        ),
        "backstory": (
            "Former sanctions-list analyst who built entity-resolution logic at a "
            "major screening vendor."
        ),
        "crew_tools": ["EXASearch"],
        "live_sources": ["Name normaliser", "Registry aliases"],
        "model": "gpt-4o-mini",
        "icon": "tag",
        "context": [],
    },
    {
        "id": "corporate_identity_specialist",
        "order": 2,
        "role": "Corporate Identity & Registry Research Specialist",
        "task": "Resolve corporate identity",
        "goal": (
            "Resolve the full legal identity - legal name, jurisdiction, LEI via "
            "GLEIF, SEC EDGAR filings and registration number - and flag "
            "structural red flags."
        ),
        "backstory": (
            "Former KYC analyst at a global correspondent bank; entity resolution "
            "across 80+ jurisdictions."
        ),
        "crew_tools": ["EXASearch", "ScrapeWebsite", "JinaScrape"],
        "live_sources": ["GLEIF", "SEC EDGAR", "Resolution engine"],
        "model": "gpt-4o-mini",
        "icon": "id",
        "context": [],
    },
    {
        "id": "adverse_media_analyst",
        "order": 3,
        "role": "Adverse Media & Open-Source Intelligence Analyst",
        "task": "Search adverse media",
        "goal": (
            "Surface negative news coverage from the last 5 years across news "
            "archives, regulatory feeds and enforcement databases - with title, "
            "source, date and URL for each item."
        ),
        "backstory": (
            "Investigative journalist turned OSINT specialist at a major risk "
            "intelligence firm."
        ),
        "crew_tools": ["EXASearch"],
        "live_sources": ["GDELT"],
        "model": "gpt-4o-mini",
        "icon": "news",
        "context": [],
    },
    {
        "id": "litigation_analyst",
        "order": 4,
        "role": "Federal Court & Regulatory Enforcement Research Analyst",
        "task": "Research federal litigation",
        "goal": (
            "Search federal dockets (CourtListener, PACER) and regulatory "
            "enforcement (SEC, CFTC, FinCEN, DOJ, FTC) for cases naming the "
            "subject; record docket, type, court, date and status."
        ),
        "backstory": (
            "Paralegal turned legal-intelligence analyst; thousands of litigation "
            "screens for AML and third-party-risk programs."
        ),
        "crew_tools": ["EXASearch", "ScrapeWebsite", "JinaScrape"],
        "live_sources": ["CourtListener"],
        "model": "gpt-4o-mini",
        "icon": "gavel",
        "context": [],
    },
    {
        "id": "sanctions_analyst",
        "order": 5,
        "role": "Sanctions & Watchlist Screening Analyst",
        "task": "Screen sanctions & watchlists",
        "goal": (
            "Screen the subject and every alias against OFAC SDN and major "
            "watchlists; return NO_MATCH / MATCH / COVERAGE_GAP with a confidence "
            "score and match type for each hit."
        ),
        "backstory": (
            "Certified CAMS professional; thousands of entity screens across "
            "global watchlists."
        ),
        "crew_tools": ["EXASearch", "ScrapeWebsite"],
        "live_sources": ["OFAC SDN"],
        "model": "gpt-4o-mini",
        "icon": "shield",
        "context": ["entity_name_variant_specialist"],
    },
    {
        "id": "ownership_analyst",
        "order": 6,
        "role": "Beneficial Ownership & Corporate Structure Analyst",
        "task": "Map beneficial ownership",
        "goal": (
            "Trace subsidiaries, parents and UBOs from public filings and flag "
            "shell-company indicators: nominee directors, PO-box addresses, "
            "circular ownership and multi-layer offshore structures."
        ),
        "backstory": (
            "UBO-tracing specialist from a financial intelligence unit; trained on "
            "ownership-obfuscation patterns."
        ),
        "crew_tools": ["EXASearch", "ScrapeWebsite"],
        "live_sources": ["GLEIF parents", "SEC Form 4 officers"],
        "model": "gpt-4o-mini",
        "icon": "network",
        "context": ["corporate_identity_specialist"],
    },
    {
        "id": "sentiment_specialist",
        "order": 7,
        "role": "Media Sentiment Scoring & Risk Classification Specialist",
        "task": "Score sentiment & classify risk",
        "goal": (
            "Classify each article's sentiment, assign a risk category and score "
            "source objectivity, so sensational or low-credibility outlets are "
            "weighted down before severity is assessed."
        ),
        "backstory": (
            "Behavioural data scientist in NLP sentiment analysis and media "
            "credibility scoring."
        ),
        "crew_tools": ["EXASearch"],
        "live_sources": ["Risk taxonomy", "Bias analyzer"],
        "model": "gpt-4o-mini",
        "icon": "chart",
        "context": ["adverse_media_analyst"],
    },
    {
        "id": "risk_synthesis_specialist",
        "order": 8,
        "role": "Integrated Risk Scoring & Report Authoring Specialist",
        "task": "Synthesise the risk report",
        "goal": (
            "Fuse every specialist output into one auditable report. Weight the "
            "signals, produce a 0-100 composite and a LOW/MEDIUM/HIGH/CRITICAL "
            "band, and cite the source of every claim."
        ),
        "backstory": (
            "Senior risk-analytics lead; designed rating methodologies for global "
            "banks' third-party-risk programs."
        ),
        "crew_tools": [],
        "live_sources": ["Risk engine", "Claude reasoning"],
        "model": "gpt-4o-mini",
        "icon": "scale",
        "context": [
            "sanctions_analyst",
            "ownership_analyst",
            "sentiment_specialist",
            "litigation_analyst",
        ],
    },
    {
        "id": "alerting_specialist",
        "order": 9,
        "role": "Compliance Report Distribution & Email Alerting Specialist",
        "task": "Distribute report & alert",
        "goal": (
            "If the risk band is HIGH or CRITICAL, escalate a compliance alert to "
            "the risk desk with the composite score, band and egregious-harm flag. "
            "Otherwise log that no alert is required."
        ),
        "backstory": (
            "Automation specialist ensuring every compliance output is stored for "
            "audit and surfaced to the right stakeholder on escalation."
        ),
        "crew_tools": [],
        "live_sources": ["Email alerting"],
        "model": "gpt-4o-mini",
        "icon": "mail",
        "context": ["risk_synthesis_specialist"],
    },
]

# Status vocabulary the UI colour-codes:
#   done    - completed with findings
#   clear   - completed, nothing adverse found (a good result)
#   flag    - completed, an adverse signal was found
#   gap     - source failed / was inaccessible -> coverage gap
#   skipped - nothing to do (no upstream input)


def roster() -> list[dict[str, Any]]:
    """Static crew definition, safe to serialise to the client."""
    return [dict(agent) for agent in ROSTER]


def _consulted(inv: dict, key: str) -> bool | None:
    sources = inv.get("sources_consulted") or {}
    return sources.get(key)


def trace(inv: dict[str, Any]) -> dict[str, Any]:
    """Replay the crew against a finished investigation.

    Returns the static roster plus, for each agent, a `result` describing what
    that specialist actually produced from the real evidence in `inv`.
    """
    supplier = inv.get("supplier") or {}
    resolution = inv.get("entity_resolution") or {}
    sanctions = inv.get("sanctions") or {}
    media = inv.get("adverse_media") or []
    media_summary = inv.get("media_summary") or {}
    litigation = inv.get("litigation") or {}
    ownership = inv.get("ownership") or []
    risk = inv.get("risk") or {}
    agent_summary = inv.get("agent_summary") or {}
    consulted = inv.get("sources_consulted") or {}

    coverage_gaps = [name for name, ok in consulted.items() if not ok]
    results: dict[str, dict[str, Any]] = {}

    # 0 - Lead investigator / orchestration ---------------------------------
    ran = sum(1 for ok in consulted.values() if ok)
    total = len(consulted) or 5
    results["lead_investigator"] = {
        "status": "gap" if coverage_gaps else "done",
        "headline": f"{ran} of {total} sources returned data",
        "metrics": [
            {"label": "Sources OK", "value": f"{ran}/{total}"},
            {"label": "Coverage gaps", "value": len(coverage_gaps)},
            {"label": "Duration", "value": f"{inv.get('duration_seconds', 0)}s"},
        ],
        "detail": (
            "Coverage gaps: " + ", ".join(sorted(coverage_gaps)).upper()
            if coverage_gaps
            else "Every source returned within budget."
        ),
        "output": {"sources_consulted": consulted, "coverage_gaps": coverage_gaps},
    }

    # 1 - Name variants -----------------------------------------------------
    query_aliases = (inv.get("query") or {}).get("aliases") or []
    supplier_aliases = supplier.get("aliases") or []
    variants = list(dict.fromkeys([*query_aliases, *supplier_aliases]))
    results["entity_name_variant_specialist"] = {
        "status": "done" if variants else "clear",
        "headline": (
            f"{len(variants)} name variant(s) expanded for screening"
            if variants
            else "No additional aliases in registries"
        ),
        "metrics": [{"label": "Variants", "value": len(variants)}],
        "detail": ", ".join(variants[:8]) if variants else "Screened on the legal name only.",
        "output": {"variants": variants},
    }

    # 2 - Corporate identity ------------------------------------------------
    selected = resolution.get("selected")
    status = supplier.get("status", "unverified")
    id_status = {
        "verified": "done",
        "probable": "done",
    }.get(status, "flag")
    results["corporate_identity_specialist"] = {
        "status": id_status,
        "headline": (
            f"Identity {status} at {supplier.get('identity_confidence', 0):.2f} confidence"
        ),
        "metrics": [
            {"label": "Status", "value": status},
            {"label": "Confidence", "value": f"{supplier.get('identity_confidence', 0):.2f}"},
            {"label": "LEI", "value": supplier.get("lei") or "-"},
            {"label": "CIK", "value": supplier.get("cik") or "-"},
        ],
        "detail": (
            (selected or {}).get("explanation")
            or "No registry record cleared the match threshold; identity unverified."
        ),
        "output": {"selected": selected, "supplier": supplier},
    }

    # 3 - Adverse media -----------------------------------------------------
    media_ran = _consulted(inv, "gdelt")
    n_media = len(media)
    results["adverse_media_analyst"] = {
        "status": ("flag" if n_media else "clear") if media_ran is not False else "gap",
        "headline": (
            f"{n_media} adverse article(s) from {media_summary.get('sources', 0)} source(s)"
            if media_ran is not False
            else "GDELT unavailable - adverse media is a coverage gap"
        ),
        "metrics": [
            {"label": "Articles", "value": n_media},
            {"label": "Sources", "value": media_summary.get("sources", 0)},
            {"label": "Peak severity", "value": f"{media_summary.get('peak_severity', 0):.2f}"},
        ],
        "detail": (
            (media[0].get("title", "") if media else "No adverse coverage matched the subject.")
        ),
        "output": {"count": n_media, "summary": media_summary},
    }

    # 4 - Litigation --------------------------------------------------------
    cases = litigation.get("cases") or []
    lit_available = litigation.get("available", True)
    if not lit_available:
        exposure = "unknown"
    elif not cases:
        exposure = "NONE"
    elif len(cases) >= 10:
        exposure = "HIGH"
    elif len(cases) >= 3:
        exposure = "MEDIUM"
    else:
        exposure = "LOW"
    results["litigation_analyst"] = {
        "status": "gap" if not lit_available else ("flag" if cases else "clear"),
        "headline": (
            f"{len(cases)} federal docket(s) found"
            if lit_available
            else "CourtListener inaccessible - litigation is a coverage gap"
        ),
        "metrics": [
            {"label": "Dockets", "value": len(cases)},
            {"label": "Exposure", "value": exposure},
        ],
        "detail": (
            (cases[0].get("case", "") if cases else litigation.get("note", "No matching dockets."))
        ),
        "output": {"cases": cases[:10], "note": litigation.get("note")},
    }

    # 5 - Sanctions ---------------------------------------------------------
    sanc_ran = _consulted(inv, "ofac")
    matched = sanctions.get("match")
    matched_entity = sanctions.get("matched_entity") or {}
    results["sanctions_analyst"] = {
        "status": "flag" if matched else ("clear" if sanc_ran is not False else "gap"),
        "headline": (
            f"MATCH - {matched_entity.get('name', 'sanctioned entity')}"
            if matched
            else (
                f"No match against {sanctions.get('list_size', 0):,} SDN names"
                if sanc_ran is not False
                else "OFAC list unavailable - sanctions is a coverage gap"
            )
        ),
        "metrics": [
            {"label": "Result", "value": "MATCH" if matched else "NO MATCH"},
            {"label": "SDN names", "value": f"{sanctions.get('list_size', 0):,}"},
            {"label": "Confidence", "value": sanctions.get("confidence", 0)},
        ],
        "detail": (
            f"{matched_entity.get('program', 'sanctions program')}: "
            + (matched_entity.get("remarks") or "")[:200]
            if matched
            else "Subject and all aliases screened clean against the SDN list."
        ),
        "output": {"match": bool(matched), "sanctions": sanctions},
    }

    # 6 - Ownership ---------------------------------------------------------
    parents = [o for o in ownership if "parent" in (o.get("relationship_type") or "")]
    officers = [o for o in ownership if o not in parents]
    results["ownership_analyst"] = {
        "status": "done" if ownership else "clear",
        "headline": (
            f"{len(officers)} officer(s), {len(parents)} corporate parent(s)"
            if ownership
            else "No related parties disclosed in public filings"
        ),
        "metrics": [
            {"label": "Related parties", "value": len(ownership)},
            {"label": "Officers", "value": len(officers)},
            {"label": "Parents", "value": len(parents)},
        ],
        "detail": (
            ", ".join(o.get("name", "") for o in ownership[:5])
            if ownership
            else "Non-US entities have no Section 16 officer disclosure obligation."
        ),
        "output": {"ownership": ownership[:20]},
    }

    # 7 - Sentiment / classification ---------------------------------------
    bias = media_summary.get("bias") or {}
    categories = media_summary.get("categories") or []
    results["sentiment_specialist"] = {
        "status": "done" if n_media else "skipped",
        "headline": (
            f"{bias.get('factual', 0)} factual / {bias.get('mixed', 0)} mixed / "
            f"{bias.get('polarized', 0)} polarized"
            if n_media
            else "No articles to classify"
        ),
        "metrics": [
            {"label": "Top category", "value": categories[0]["label"] if categories else "-"},
            {"label": "Polarized share", "value": f"{bias.get('polarized_share', 0):.0%}"},
            {"label": "Categories", "value": len(categories)},
        ],
        "detail": (
            "Objectivity scored per article so sensational coverage is discounted "
            "before it reaches the risk engine."
            if n_media
            else "The adverse-media stage returned nothing to score."
        ),
        "output": {"bias": bias, "categories": categories},
    }

    # 8 - Risk synthesis ----------------------------------------------------
    level = risk.get("level", "low")
    results["risk_synthesis_specialist"] = {
        "status": "flag" if level in ("high", "critical") else "done",
        "headline": f"Composite {risk.get('score', 0)} / 100 - {level.upper()}",
        "metrics": [
            {"label": "Score", "value": risk.get("score", 0)},
            {"label": "Band", "value": level.upper()},
            {"label": "Signals", "value": len(risk.get("contributions") or [])},
        ],
        "detail": (
            agent_summary.get("summary")
            or agent_summary.get("recommendation")
            or "Weighted synthesis of every specialist output."
        ),
        "output": {"risk": risk, "recommendation": agent_summary.get("recommendation")},
    }

    # 9 - Alerting ----------------------------------------------------------
    escalate = level in ("high", "critical")
    subject_name = supplier.get("name") or (inv.get("query") or {}).get("name") or "subject"
    results["alerting_specialist"] = {
        "status": "flag" if escalate else "clear",
        "headline": (
            f"Compliance alert escalated to {ALERT_RECIPIENT}"
            if escalate
            else "No alert required - risk band is LOW/MEDIUM"
        ),
        "metrics": [
            {"label": "Action", "value": "ALERT" if escalate else "No alert"},
            {"label": "Band", "value": level.upper()},
        ],
        "detail": (
            f'Subject line: "[COMPLIANCE ALERT] RISK DETECTED - {subject_name}"'
            if escalate
            else "Escalation threshold (HIGH/CRITICAL) not met; logged for audit only."
        ),
        "output": {"escalated": escalate, "recipient": ALERT_RECIPIENT if escalate else None},
    }

    return {
        "subject": subject_name,
        "risk_level": level,
        "risk_score": risk.get("score", 0),
        "coverage_gaps": coverage_gaps,
        "agents": [
            {**dict(agent), "result": results.get(agent["id"], {})} for agent in ROSTER
        ],
    }
