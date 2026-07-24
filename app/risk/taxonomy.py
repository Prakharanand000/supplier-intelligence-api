"""Adverse-media risk taxonomy.

Maps headline vocabulary to risk categories and a severity weight. This is what
drives the tagging filters in the dashboard: an article is not simply
"negative", it is tagged Financial Crime / Sanctions / Labor, each with its own
weight, so an analyst can filter to the risk types they actually care about.

Severity is per-term, because "indicted" and "settlement" are not the same
finding even though both are adverse.
"""

from __future__ import annotations

RISK_TAXONOMY: dict[str, dict] = {
    "financial_crime": {
        "label": "Financial Crime",
        "terms": {
            "money laundering": 1.0, "laundering": 0.95, "embezzlement": 0.95,
            "fraud": 1.0, "fraudulent": 0.95, "ponzi": 1.0, "tax evasion": 0.9,
            "wire fraud": 1.0, "securities fraud": 1.0, "accounting fraud": 1.0,
        },
    },
    "bribery_corruption": {
        "label": "Bribery & Corruption",
        "terms": {
            "bribery": 1.0, "bribe": 0.95, "corruption": 0.95, "kickback": 0.9,
            "graft": 0.85, "fcpa": 0.95,
        },
    },
    "sanctions": {
        "label": "Sanctions & Export Control",
        "terms": {
            "sanctioned": 1.0, "sanctions": 0.9, "embargo": 0.85,
            "export control": 0.8, "ofac": 0.9, "sanctions evasion": 1.0,
        },
    },
    "criminal": {
        "label": "Criminal Proceedings",
        "terms": {
            "indicted": 1.0, "indictment": 1.0, "convicted": 1.0,
            "pleaded guilty": 1.0, "guilty": 0.9, "arrested": 0.85,
            "criminal charges": 0.95, "raid": 0.8, "prosecutors": 0.8,
        },
    },
    "litigation": {
        "label": "Litigation",
        "terms": {
            "lawsuit": 0.7, "sued": 0.7, "litigation": 0.65,
            "class action": 0.75, "subpoena": 0.7, "settlement": 0.55,
            "damages": 0.6,
        },
    },
    "regulatory": {
        "label": "Regulatory Action",
        "terms": {
            "investigation": 0.7, "probe": 0.75, "penalty": 0.7, "fined": 0.75,
            "fine": 0.6, "violation": 0.7, "antitrust": 0.75,
            "regulator": 0.65, "enforcement action": 0.85, "sec charges": 0.9,
        },
    },
    "cyber": {
        "label": "Cyber & Data",
        "terms": {
            "data breach": 0.8, "breach": 0.6, "hacked": 0.8, "hack": 0.7,
            "ransomware": 0.85, "cyberattack": 0.8, "data leak": 0.75,
        },
    },
    "environmental": {
        "label": "Environmental",
        "terms": {
            "pollution": 0.75, "contamination": 0.8, "oil spill": 0.85,
            "toxic": 0.75, "emissions scandal": 0.9, "environmental violation": 0.8,
        },
    },
    "labor_human_rights": {
        "label": "Labor & Human Rights",
        "terms": {
            "forced labor": 1.0, "child labor": 1.0, "human trafficking": 1.0,
            "modern slavery": 1.0, "discrimination": 0.7, "harassment": 0.7,
            "unsafe working": 0.75, "wage theft": 0.8,
        },
    },
    "product_safety": {
        "label": "Product Safety",
        "terms": {
            "recall": 0.65, "defective": 0.75, "contaminated": 0.8,
            "safety violation": 0.8, "injuries": 0.6,
        },
    },
    "governance": {
        "label": "Governance",
        "terms": {
            "misconduct": 0.8, "insider trading": 0.9, "whistleblower": 0.7,
            "conflict of interest": 0.7, "resigns amid": 0.75,
            "ousted": 0.65, "accounting irregularities": 0.9,
        },
    },
}

# Terms sent to GDELT's search API. Deliberately a curated subset of the
# taxonomy above: the full term list produces a query long enough to be
# rejected, and these are the high-recall anchors. Tagging still uses the
# complete taxonomy.
SEARCH_TERMS = [
    "fraud", "corruption", "bribery", "lawsuit", "investigation",
    "sanctions", "money laundering", "indictment", "settlement",
    "penalty", "misconduct", "violation", "recall",
]


def categories_for(text: str) -> list[dict]:
    """Tag a headline with every risk category it matches, most severe first."""
    lowered = (text or "").lower()
    tagged: list[dict] = []

    for key, spec in RISK_TAXONOMY.items():
        hits = [term for term in spec["terms"] if term in lowered]
        if not hits:
            continue
        tagged.append(
            {
                "key": key,
                "label": spec["label"],
                "severity": max(spec["terms"][term] for term in hits),
                "matched_terms": sorted(hits, key=len, reverse=True)[:4],
            }
        )

    tagged.sort(key=lambda c: c["severity"], reverse=True)
    return tagged


def category_labels() -> dict[str, str]:
    return {key: spec["label"] for key, spec in RISK_TAXONOMY.items()}
