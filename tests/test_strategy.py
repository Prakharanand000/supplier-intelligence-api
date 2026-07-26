"""Strategy board tests - offline behaviour must stay deterministic and every
sample must satisfy the structured-output schema the live path also produces."""

from __future__ import annotations

import asyncio

import pytest

from app import strategy
from app.strategy import board, samples


def test_samples_match_the_schema_shape():
    for sample in samples.SAMPLES.values():
        # verdict
        assert sample["verdict"]["decision"] in board.DECISIONS
        assert 0 <= sample["verdict"]["confidence"] <= 100
        for k in ("financial_risk", "regulatory_risk", "execution_risk"):
            assert sample["verdict"][k] in board.RISK_LEVELS
        # five seats, each a known key
        keys = {s["seat"] for s in sample["seats"]}
        assert keys == {s["key"] for s in board.SEATS}
        # board vote covers all four members
        members = {v["member"] for v in sample["board_vote"]}
        assert members == set(board.BOARD_MEMBERS)
        # audited claim verdicts are valid
        for claim in sample["evidence_audit"]["audited_claims"]:
            assert claim["verdict"] in board.CLAIM_VERDICTS


def test_get_sample_decorates_and_orders():
    decision = board.get_sample("salesforce_notion")
    # seats returned in canonical board order with role + icon attached
    assert [s["seat"] for s in decision["seats"]] == [s["key"] for s in board.SEATS]
    assert all("role" in s and "icon" in s for s in decision["seats"])
    # attacks sorted by (deal_breaker, severity) descending
    sev = [(a["deal_breaker"], a["severity"]) for a in decision["attacks"]]
    assert sev == sorted(sev, reverse=True)
    assert decision["attacks"][0]["deal_breaker"] is True


def test_match_maps_questions_to_samples():
    assert samples.match("Should Salesforce acquire Notion?") == "salesforce_notion"
    assert samples.match("should ADOBE buy figma") == "adobe_figma"
    assert samples.match("Spotify audiobooks tier?") == "spotify_audiobooks"
    assert samples.match("Should Acme buy Globex?") is None


def test_decide_without_key_returns_matching_sample():
    out = asyncio.run(strategy.decide("Should Salesforce acquire Notion?"))
    assert out["verdict"]["decision"] == "NO-GO"
    assert "no ANTHROPIC_API_KEY" in out["generated_by"]


def test_decide_without_key_and_no_match_is_a_structured_notice():
    out = asyncio.run(strategy.decide("Should Acme buy Globex?"))
    assert out["available"] is False
    assert out["notice"]
    assert len(out["samples"]) == len(samples.SAMPLES)


def test_list_samples_are_lightweight_cards():
    cards = strategy.list_samples()
    assert {c["id"] for c in cards} == set(samples.SAMPLES)
    for c in cards:
        assert set(c) == {"id", "question", "decision", "confidence", "decision_type"}
