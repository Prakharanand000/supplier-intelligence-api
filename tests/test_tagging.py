"""Tests for risk tagging, DOB corroboration and dashboard aggregation."""

from __future__ import annotations

from app.pipeline import _summarize_media
from app.sources.gdelt import _MARKET_NOISE
from app.risk.taxonomy import categories_for, category_labels
from app.sources.ofac import _check_dob, _dob_years
from app.sources.sec import _parse_form4


# --- adverse media tagging -------------------------------------------------
def test_headline_tagged_with_every_matching_category():
    keys = {c["key"] for c in categories_for("Firm sued over bribery and fraud")}
    assert {"litigation", "bribery_corruption", "financial_crime"} <= keys


def test_categories_are_ordered_most_severe_first():
    tagged = categories_for("Executive indicted after settlement talks collapse")
    assert tagged[0]["severity"] >= tagged[-1]["severity"]
    assert tagged[0]["key"] == "criminal"


def test_severity_distinguishes_indictment_from_settlement():
    indicted = categories_for("CEO indicted")[0]["severity"]
    settled = categories_for("Company reaches settlement")[0]["severity"]
    assert indicted > settled


def test_untagged_headline_returns_nothing():
    assert categories_for("Company opens new distribution centre") == []
    assert categories_for("") == []


def test_multiword_terms_match():
    keys = {c["key"] for c in categories_for("Supplier accused of forced labor")}
    assert "labor_human_rights" in keys


def test_every_category_has_a_label():
    labels = category_labels()
    for tagged in categories_for("fraud lawsuit breach recall pollution"):
        assert labels[tagged["key"]] == tagged["label"]


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
