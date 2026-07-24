"""Tests for risk tagging, DOB corroboration and dashboard aggregation."""

from __future__ import annotations

from app.demo import build_investigation, list_subjects
from app.demo.dataset import ARTICLES, SUBJECTS
from app.pipeline import _summarize_media
from app.risk import bias
from app.sources.gdelt import _MARKET_NOISE
from app.risk.taxonomy import CATEGORY_ORDER, categories_for, category_labels
from app.sources.ofac import _check_dob, _dob_years
from app.sources.sec import _parse_form4


# --- adverse media tagging (5 top-level categories) ------------------------
def test_headline_tagged_with_every_matching_category():
    keys = {c["key"] for c in categories_for("Firm sued over bribery and fraud")}
    # "sued" -> legal_reputational; "bribery"/"fraud" -> financial_crime
    assert {"legal_reputational", "financial_crime"} <= keys


def test_categories_are_ordered_most_severe_first():
    tagged = categories_for("Executive indicted after settlement talks collapse")
    assert tagged[0]["severity"] >= tagged[-1]["severity"]
    assert tagged[0]["key"] == "terrorism_serious_crime"  # "indicted"


def test_severity_distinguishes_indictment_from_settlement():
    indicted = categories_for("CEO indicted")[0]["severity"]
    settled = categories_for("Company reaches settlement")[0]["severity"]
    assert indicted > settled


def test_untagged_headline_returns_nothing():
    assert categories_for("Company opens new distribution centre") == []
    assert categories_for("") == []


def test_multiword_terms_match():
    keys = {c["key"] for c in categories_for("Supplier accused of forced labor")}
    assert "terrorism_serious_crime" in keys


def test_exactly_five_categories_each_with_a_label_and_color():
    labels = category_labels()
    assert len(labels) == 5
    assert [c["key"] for c in labels] == CATEGORY_ORDER
    for c in labels:
        assert c["label"] and c["color"].startswith("#")


def test_sanctions_and_regulatory_are_distinct_categories():
    assert categories_for("Entity added to OFAC SDN list")[0]["key"] == "sanctions"
    assert "regulatory" in {c["key"] for c in categories_for("FINRA censures broker")}


# --- media bias / objectivity analysis -------------------------------------
def test_factual_wire_copy_scores_low():
    result = bias.analyze(
        "Regulators fined the company $12 million. It said it strengthened "
        "controls. No individuals were charged."
    )
    assert result["label"] == "Factual"
    assert result["flagged_count"] == 0


def test_loaded_tabloid_copy_scores_polarized():
    result = bias.analyze(
        "In a shocking scandal, insiders say the crooked bosses reportedly "
        "laundered staggering sums. Everyone knows this is the tip of the iceberg."
    )
    assert result["label"] == "Polarized"
    assert result["flagged_count"] >= 2


def test_bias_flags_point_at_specific_terms():
    result = bias.analyze("The firm was obviously reckless and utterly negligent.")
    flagged = [s for s in result["sentences"] if s["biased"]]
    assert flagged
    terms = {t.lower() for s in flagged for r in s["reasons"] for t in r["terms"]}
    assert {"obviously", "reckless", "utterly"} & terms


def test_bias_spans_are_within_sentence_bounds():
    s = "This is clearly the worst and most shocking outcome imaginable."
    result = bias.analyze(s)
    for sent in result["sentences"]:
        for span in sent["spans"]:
            assert 0 <= span["start"] < span["end"] <= len(sent["text"])


def test_empty_body_is_unrated():
    assert bias.analyze("")["label"] == "Unrated"


# --- demo dataset integrity ------------------------------------------------
def test_demo_has_between_30_and_40_articles():
    assert 30 <= len(ARTICLES) <= 40


def test_every_demo_article_tags_to_at_least_one_category():
    for art in ARTICLES:
        tags = categories_for(f"{art['title']} {art['body']}")
        assert tags, art["title"]


def test_demo_dataset_spans_all_five_categories():
    seen = set()
    for art in ARTICLES:
        for c in categories_for(f"{art['title']} {art['body']}"):
            seen.add(c["key"])
    assert set(CATEGORY_ORDER) <= seen


def test_demo_dataset_has_factual_and_polarized_articles():
    labels = {bias.analyze(a["body"])["label"] for a in ARTICLES}
    assert "Factual" in labels and "Polarized" in labels


def test_build_investigation_produces_full_object():
    for sid in SUBJECTS:
        inv = build_investigation(sid)
        assert inv["demo"] is True
        assert inv["adverse_media"], sid
        assert "bias" in inv["media_summary"]
        assert inv["risk"]["level"] in ("low", "medium", "high", "critical")
        for graph in inv["graph"].values():
            assert "nodes" in graph and "edges" in graph


def test_list_subjects_matches_dataset():
    subjects = list_subjects()
    assert {s["id"] for s in subjects} == set(SUBJECTS)
    for s in subjects:
        assert s["article_count"] > 0


# --- connection network graph ----------------------------------------------
def test_demo_network_is_multihop_and_cross_entity():
    net = build_investigation("northwind")["graph"]["network"]
    ids = {n["id"] for n in net["nodes"]}
    assert len(net["nodes"]) >= 8  # not a flat star
    # a person links to an external firm (2-hop), not just to the subject
    types = {n["id"]: n["type"] for n in net["nodes"]}
    person_to_company = any(
        types.get(e["source"]) == "person" and types.get(e["target"]) == "company"
        for e in net["edges"]
    )
    assert person_to_company
    # a shared officer links Northwind to another investigated entity
    assert "meridian-capital-partners" in ids or "halcyon-logistics-ltd" in ids


def test_network_edges_carry_facts_for_insight():
    net = build_investigation("meridian")["graph"]["network"]
    assert net["edges"]
    for e in net["edges"]:
        assert e["relationship"] and e["description"]
        assert 0 <= e["confidence"] <= 1


def test_full_graph_is_superset_of_subgraph():
    g = build_investigation("halcyon")["graph"]
    sub_ids = {n["id"] for n in g["network"]["nodes"]}
    full_ids = {n["id"] for n in g["network_full"]["nodes"]}
    assert sub_ids <= full_ids
    assert len(full_ids) > len(sub_ids)  # room to expand


def test_connection_insight_fallback_names_both_parties():
    import asyncio

    from app.agent.insight import connection_insight

    payload = {
        "kind": "edge", "subject": "Northwind Trading Co.", "risk_level": "high",
        "source_label": "Peter Vance", "source_type": "person",
        "target_label": "Meridian Capital Partners", "target_type": "entity",
        "relationship": "Advisory board member", "confidence": 0.66,
        "description": "Peter Vance advises Meridian Capital Partners.",
    }
    result = asyncio.run(connection_insight(payload))
    assert "Peter Vance" in result["insight"]
    assert "Meridian Capital Partners" in result["insight"]
    assert "deterministic" in result["generated_by"]  # no API key in test env


# --- market-wire noise -----------------------------------------------------
def test_analyst_wire_copy_is_not_adverse_media():
    """The bank is the analyst here, not the subject of an allegation."""
    for headline in [
        "Shake Shack (NYSE: SHAK) Price Target Cut to $80.00 by Wells Fargo & Company",
        "Acme Corp Shares Sold by Wells Fargo & Company",
        "Wells Fargo & Company Reiterates Buy Rating for Widget Inc",
        "Vanguard Group Boosted Position in Acme Corp",
    ]:
        assert _MARKET_NOISE.search(headline), headline


def test_genuine_allegations_are_not_filtered_as_noise():
    for headline in [
        "Wells Fargo sued over account fraud",
        "Regulators fine Wells Fargo $1bn over compliance failures",
        "Investigation into Wells Fargo lending practices widens",
    ]:
        assert not _MARKET_NOISE.search(headline), headline


# --- media aggregation -----------------------------------------------------
def _article(title, date, severity, cats):
    return {
        "title": title, "date": date, "severity": severity, "source": "example.com",
        "categories": [{"key": k, "label": k, "severity": severity} for k in cats],
        "category_keys": cats,
    }


def test_summary_counts_by_category_and_month():
    summary = _summarize_media([
        _article("a", "2026-01-04", 1.0, ["financial_crime"]),
        _article("b", "2026-01-19", 0.7, ["financial_crime", "litigation"]),
        _article("c", "2026-03-02", 0.6, ["litigation"]),
    ])
    counts = {c["key"]: c["count"] for c in summary["categories"]}
    assert counts == {"financial_crime": 2, "litigation": 2}
    assert summary["total"] == 3
    assert summary["peak_severity"] == 1.0
    assert summary["timeline"] == [
        {"month": "2026-01", "count": 2}, {"month": "2026-03", "count": 1}
    ]


def test_summary_handles_no_media():
    summary = _summarize_media([])
    assert summary["total"] == 0 and summary["categories"] == []


# --- OFAC date-of-birth corroboration --------------------------------------
def test_dob_years_parsed_from_remarks():
    assert _dob_years("DOB 05 Feb 1963; POB Tehran, Iran") == {"1963"}


def test_dob_match_corroborates():
    assert _check_dob("1963-02-05", "DOB 05 Feb 1963; nationality Iran")["status"] == "match"


def test_dob_conflict_is_reported_not_averaged_away():
    result = _check_dob("1990-01-01", "DOB 05 Feb 1963")
    assert result["status"] == "conflict"
    assert "1963" in result["listed_years"]


def test_dob_unavailable_when_entry_has_none():
    assert _check_dob("1963", "POB Tehran, Iran")["status"] == "unavailable"


def test_no_dob_supplied_means_no_check():
    assert _check_dob(None, "DOB 05 Feb 1963") is None


# --- Form 4 parsing --------------------------------------------------------
FORM4 = """<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>SMITH JANE Q</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>1</isDirector><officerTitle>EVP &amp; CFO</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>2026-05-01</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>150.25</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def test_form4_yields_owner_role_and_transaction():
    parsed = _parse_form4(FORM4)
    assert parsed["owner"] == "SMITH JANE Q"
    assert parsed["role"] == "EVP & CFO"  # XML entity decoded
    assert parsed["is_director"] is True

    txn = parsed["transactions"][0]
    assert txn["direction"] == "disposed"
    assert txn["code_label"] == "Open-market sale"
    assert txn["shares"] == 1000.0
    assert txn["value"] == 150250.0


def test_form4_falls_back_to_regex_on_unparseable_document():
    html_view = "<html><body><rptOwnerName>DOE JOHN</rptOwnerName></body></html>"
    parsed = _parse_form4(html_view)
    assert parsed["owner"] == "DOE JOHN"
    assert parsed["transactions"] == []


def test_form4_without_owner_is_discarded():
    assert _parse_form4("<ownershipDocument></ownershipDocument>") is None
