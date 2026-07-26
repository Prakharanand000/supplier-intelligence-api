"""Crew trace tests - the ported multi-agent crew must stay grounded in the
real investigation evidence, never invent a status, and always cover coverage
gaps."""

from __future__ import annotations

from app import crew

ALL_OK = {"ofac": True, "sec": True, "gleif": True, "gdelt": True, "courtlistener": True}


def _investigation(**overrides) -> dict:
    base = {
        "query": {"name": "Acme Ltd", "aliases": ["Acme Limited"]},
        "supplier": {
            "name": "Acme Ltd",
            "status": "verified",
            "identity_confidence": 0.9,
            "aliases": ["Acme Limited", "Acme"],
            "lei": "LEI123",
            "cik": None,
        },
        "entity_resolution": {"selected": {"explanation": "matched on name + LEI"}},
        "sanctions": {"match": False, "confidence": 0.0, "list_size": 39564},
        "adverse_media": [],
        "media_summary": {
            "sources": 0,
            "peak_severity": 0.0,
            "bias": {"factual": 0, "mixed": 0, "polarized": 0, "polarized_share": 0.0},
            "categories": [],
        },
        "litigation": {"available": True, "cases": []},
        "ownership": [],
        "risk": {"score": 0, "level": "low", "contributions": []},
        "agent_summary": {"recommendation": "Proceed"},
        "sources_consulted": dict(ALL_OK),
        "duration_seconds": 3.2,
    }
    base.update(overrides)
    return base


def test_roster_has_ten_agents_in_task_order():
    agents = crew.roster()
    assert len(agents) == 10
    assert [a["order"] for a in agents] == list(range(10))
    # every agent carries the fields the UI renders
    for a in agents:
        assert a["role"] and a["task"] and "live_sources" in a


def test_trace_covers_every_agent():
    trace = crew.trace(_investigation())
    assert len(trace["agents"]) == 10
    assert all(a["result"].get("status") for a in trace["agents"])


def test_clean_supplier_produces_no_alert():
    trace = crew.trace(_investigation())
    alerting = trace["agents"][-1]["result"]
    assert alerting["status"] == "clear"
    assert "No alert required" in alerting["headline"]
    assert alerting["output"]["escalated"] is False


def test_high_risk_escalates_to_alert_recipient():
    trace = crew.trace(
        _investigation(risk={"score": 72, "level": "high", "contributions": [{}]})
    )
    alerting = trace["agents"][-1]["result"]
    assert alerting["status"] == "flag"
    assert alerting["output"]["escalated"] is True
    assert alerting["output"]["recipient"] == crew.ALERT_RECIPIENT
    assert crew.ALERT_RECIPIENT in alerting["headline"]


def test_sanctions_match_is_flagged():
    trace = crew.trace(
        _investigation(
            sanctions={
                "match": True,
                "confidence": 0.97,
                "list_size": 39564,
                "matched_entity": {"name": "ACME LTD", "program": "SDGT", "remarks": "x"},
            }
        )
    )
    sanctions = next(a for a in trace["agents"] if a["id"] == "sanctions_analyst")
    assert sanctions["result"]["status"] == "flag"
    assert "MATCH" in sanctions["result"]["headline"]


def test_failed_source_is_reported_as_coverage_gap():
    consulted = dict(ALL_OK, courtlistener=False)
    trace = crew.trace(
        _investigation(
            sources_consulted=consulted,
            litigation={"available": False, "cases": [], "note": "no token"},
        )
    )
    assert "courtlistener" in trace["coverage_gaps"]
    lit = next(a for a in trace["agents"] if a["id"] == "litigation_analyst")
    assert lit["result"]["status"] == "gap"
    lead = trace["agents"][0]["result"]
    assert lead["status"] == "gap"
