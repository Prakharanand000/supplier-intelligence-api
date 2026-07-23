"""Offline tests for normalization, similarity and the resolution engine.

No network, no database - these cover the component the product actually
depends on being right.

    python -m pytest tests -q
"""

from __future__ import annotations

import asyncio

from app.resolution.engine import EntityRecord, resolve, verdict
from app.resolution.normalize import (
    normalize_country,
    normalize_domain,
    normalize_name,
)
from app.resolution.similarity import (
    jaro_winkler,
    levenshtein,
    levenshtein_ratio,
    name_similarity,
)


# --- normalization ---------------------------------------------------------
def test_legal_suffixes_collapse():
    assert normalize_name("ABC Manufacturing LLC") == "abc manufacturing"
    assert normalize_name("ABC Manufacturing Ltd.") == "abc manufacturing"
    assert normalize_name("ABC Manufacturing GmbH") == "abc manufacturing"


def test_normalize_never_empties_a_name():
    assert normalize_name("The Group Ltd") != ""


def test_accents_and_punctuation():
    assert normalize_name("Société Générale S.A.") == "societe generale"


def test_ampersand_and_and_collapse_identically():
    # "&" is expanded to "and", which is then dropped as a stopword, so both
    # spellings of the same company normalize to one key.
    assert normalize_name("Smith & Jones, Inc.") == "smith jones"
    assert normalize_name("Smith and Jones Inc") == "smith jones"


def test_country_aliases():
    assert normalize_country("USA") == "united states"
    assert normalize_country("U.S.A.") == "united states"
    assert normalize_country("UK") == "united kingdom"


def test_domain_extraction():
    assert normalize_domain("https://www.Example.com/about") == "example.com"
    assert normalize_domain("ops@example.com") == "example.com"


# --- similarity ------------------------------------------------------------
def test_levenshtein():
    assert levenshtein("kitten", "sitting") == 3
    assert levenshtein_ratio("abc", "abc") == 1.0


def test_jaro_winkler_prefers_shared_prefix():
    assert jaro_winkler("acme corp", "acme corporation") > jaro_winkler(
        "acme corp", "zzzz corporation"
    )


def test_name_similarity_survives_word_order():
    score = name_similarity("manufacturing abc", "abc manufacturing")["score"]
    assert score > 0.7


# --- resolution engine -----------------------------------------------------
def _record(**kwargs) -> EntityRecord:
    kwargs.setdefault("source", "TEST")
    return EntityRecord(**kwargs)


def test_resolves_across_legal_forms():
    candidates = [
        _record(name="ABC Manufacturing LLC", country="United States"),
        _record(name="Zephyr Logistics Inc", country="United States"),
    ]
    results = asyncio.run(
        resolve(
            query_name="ABC Manufacturing Ltd",
            candidates=candidates,
            query_country="USA",
        )
    )
    assert results[0].record.name == "ABC Manufacturing LLC"
    assert results[0].matched
    assert results[0].confidence > results[1].confidence


def test_website_and_ownership_lift_a_weaker_name_match():
    shared_officer = "Jane Q Smith"
    weak_name_strong_evidence = _record(
        name="ABC Manufacturing Group",
        country="United States",
        website="https://abc-mfg.com",
        officers=[shared_officer],
    )
    strong_name_no_evidence = _record(
        name="ABC Manufacturing Ltd",
        country="Germany",
    )
    results = asyncio.run(
        resolve(
            query_name="ABC Manufacturing Ltd",
            candidates=[weak_name_strong_evidence, strong_name_no_evidence],
            query_country="United States",
            query_website="http://www.abc-mfg.com/contact",
            query_officers=[shared_officer],
        )
    )
    top = results[0]
    assert top.record.website == "https://abc-mfg.com"
    assert top.breakdown["website"] == 1.0
    assert top.breakdown["ownership"] == 1.0


def test_record_gets_no_ownership_credit_from_its_own_officers():
    """Self-corroboration would hand every candidate a free 1.0."""
    only_candidate = _record(
        source="SEC", name="ABC Manufacturing LLC", officers=["Jane Q Smith"]
    )
    results = asyncio.run(
        resolve(query_name="ABC Manufacturing Ltd", candidates=[only_candidate])
    )
    assert "ownership" not in results[0].breakdown


def test_ownership_fires_on_cross_source_corroboration():
    shared = "Jane Q Smith"
    sec = _record(source="SEC", name="ABC Manufacturing LLC", officers=[shared])
    gleif = _record(source="GLEIF", name="ABC Manufacturing Ltd", officers=[shared])
    results = asyncio.run(
        resolve(query_name="ABC Manufacturing", candidates=[sec, gleif])
    )
    # Each record is corroborated by the *other* source, not by itself.
    assert all(r.breakdown.get("ownership") == 1.0 for r in results)


def test_weights_renormalize_over_available_features():
    """A candidate with only a name must not be penalised for missing fields."""
    results = asyncio.run(
        resolve(query_name="Acme Corp", candidates=[_record(name="Acme Corporation")])
    )
    weights = results[0].weights_used
    assert abs(sum(weights.values()) - 1.0) < 1e-6
    assert set(weights) <= {"name", "embedding"}


def test_confidence_is_not_hardcoded():
    close = asyncio.run(
        resolve(query_name="Acme Corp", candidates=[_record(name="Acme Corporation")])
    )[0].confidence
    far = asyncio.run(
        resolve(query_name="Acme Corp", candidates=[_record(name="Globex Industries")])
    )[0].confidence
    assert close > far
    assert 0.0 <= far < close <= 1.0


def test_verdict_bands():
    assert verdict(0.95) == "verified"
    assert verdict(0.60) == "probable"
    assert verdict(0.20) == "unverified"


def test_no_candidates_returns_empty():
    assert asyncio.run(resolve(query_name="Nobody", candidates=[])) == []
