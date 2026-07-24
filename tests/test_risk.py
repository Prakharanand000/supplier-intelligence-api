"""Risk engine tests - the scoring must stay explainable and bounded."""

from __future__ import annotations

from app.risk import evaluate, recommendation

ALL_OK = {"ofac": True, "sec": True, "gleif": True, "gdelt": True, "courtlistener": True}


def _evaluate(**overrides):
    base = dict(
        sanctions={"match": False, "confidence": 0.99, "list_size": 17000},
        litigation={"available": True, "cases": []},
        adverse_media=[],
        identity_confidence=0.95,
        identity_verdict="verified",
        ownership=[],
        sources_consulted=ALL_OK,
    )
    base.update(overrides)
    return evaluate(**base)


def test_clean_supplier_is_low_risk():
    risk, signals = _evaluate()
    assert risk["score"] == 0
    assert risk["level"] == "low"
    assert signals == []


def test_sanctions_match_dominates():
    risk, _ = _evaluate(
        sanctions={
            "match": True,
            "confidence": 0.97,
            "list_size": 17000,
            "matched_entity": {"name": "BAD CO", "program": "SDGT"},
        }
    )
    assert risk["level"] == "critical"
    assert risk["score"] >= 80


def _sanctions_hit(dob_status=None):
    hit = {
        "match": True, "confidence": 1.0, "list_size": 17000,
        "matched_entity": {"name": "NASRALLAH, Hasan", "program": "SDGT"},
    }
    if dob_status:
        hit["dob_check"] = {"status": dob_status, "listed_years": ["1953"], "note": "x"}
    return hit


def test_dob_conflict_demotes_a_sanctions_hit():
    """A namesake with a different DOB must not score as a confirmed hit."""
    corroborated, _ = _evaluate(sanctions=_sanctions_hit("match"))
    conflicted, _ = _evaluate(sanctions=_sanctions_hit("conflict"))

    assert corroborated["score"] == 100 and corroborated["level"] == "critical"
    assert conflicted["score"] < corroborated["score"]
    # Demoted, but not cleared - aliases and incomplete records exist.
    assert conflicted["score"] > 0
    assert "namesake" in conflicted["reasons"][0]


def test_dob_absent_scores_the_same_as_before():
    with_dob, _ = _evaluate(sanctions=_sanctions_hit("match"))
    without, _ = _evaluate(sanctions=_sanctions_hit(None))
    assert with_dob["score"] == without["score"]


def test_score_is_capped_at_100():
    risk, _ = _evaluate(
        sanctions={
            "match": True,
            "confidence": 1.0,
            "list_size": 1,
            "matched_entity": {"name": "BAD CO", "program": "SDGT"},
        },
        litigation={
            "available": True,
            "cases": [
                {"case": f"US v. Bad Co {i}", "confidence": 0.9, "url": None}
                for i in range(10)
            ],
        },
        adverse_media=[
            {"title": "Bad Co indicted", "severity": 1.0, "confidence": 0.9, "url": None}
        ],
        identity_confidence=0.1,
        identity_verdict="unverified",
    )
    assert risk["score"] == 100
    assert risk["raw_score"] > 100  # the raw total stays visible for auditing


def test_litigation_score_does_not_scale_with_docket_count():
    """Docket volume tracks company size, not risk - it must not compound."""
    one, _ = _evaluate(
        litigation={"available": True,
                    "cases": [{"case": "A v. B", "confidence": 0.9, "url": None}]}
    )
    many, _ = _evaluate(
        litigation={"available": True,
                    "cases": [{"case": f"A v. B {i}", "confidence": 0.9, "url": None}
                              for i in range(25)]}
    )
    assert one["score"] == many["score"] == 30


def test_adverse_media_scales_with_severity_not_volume():
    mild, _ = _evaluate(
        adverse_media=[{"title": "Firm settles", "severity": 0.5,
                        "confidence": 0.8, "url": None}]
    )
    severe, _ = _evaluate(
        adverse_media=[{"title": "Firm indicted", "severity": 1.0,
                        "confidence": 0.8, "url": None}]
    )
    assert severe["score"] > mild["score"] == 10
    assert severe["score"] == 20


def test_every_point_is_attributed():
    risk, signals = _evaluate(
        adverse_media=[
            {"title": "Firm sued over fraud", "severity": 1.0,
             "confidence": 0.88, "url": "http://x"}
        ]
    )
    assert risk["raw_score"] == sum(c["points"] for c in risk["contributions"])
    assert len(risk["reasons"]) == len(signals)


def test_unavailable_source_is_a_coverage_gap_not_a_clean_bill():
    risk, _ = _evaluate(litigation={"available": False, "cases": [], "note": "no token"})
    categories = {c["category"] for c in risk["contributions"]}
    assert "coverage_gap" in categories


def test_unverified_identity_adds_risk():
    risk, _ = _evaluate(identity_confidence=0.3, identity_verdict="unverified")
    assert risk["score"] > 0
    assert any(c["category"] == "identity" for c in risk["contributions"])


def test_ownership_complexity_across_jurisdictions():
    risk, _ = _evaluate(
        ownership=[
            {"relationship_type": "direct_parent", "country": "Netherlands"},
            {"relationship_type": "ultimate_parent", "country": "Cayman Islands"},
        ]
    )
    assert any(c["category"] == "ownership_complexity" for c in risk["contributions"])


def test_recommendation_covers_every_band():
    for level in ("low", "medium", "high", "critical"):
        assert recommendation({"level": level})
