"""Adverse-media risk taxonomy.

Five top-level risk categories, each with a headline lexicon and a severity
weight. This is what drives the category filters in the dashboard: an article
is tagged Financial Crime / Legal & Reputational / Regulatory / Terrorism &
Serious Crime / Sanctions, each with its own weight, so an analyst can filter
to the risk types they care about.

Severity is per-term, because "indicted for terrorist financing" and "faces a
shareholder lawsuit" are not the same finding even though both are adverse.
"""

from __future__ import annotations

RISK_TAXONOMY: dict[str, dict] = {
    "financial_crime": {
        "label": "Financial Crime",
        "color": "#c2410c",
        "terms": {
            "money laundering": 1.0, "laundering": 0.95, "embezzlement": 0.95,
            "embezzled": 0.95, "fraud": 0.95, "fraudulent": 0.9, "ponzi": 1.0,
            "tax evasion": 0.9, "wire fraud": 1.0, "securities fraud": 1.0,
            "accounting fraud": 1.0, "bribery": 0.95, "bribe": 0.9,
            "corruption": 0.9, "kickback": 0.85, "insider trading": 0.9,
            "market manipulation": 0.9, "misappropriation": 0.85,
            "financial crime": 0.9, "illicit funds": 0.85,
        },
    },
    "legal_reputational": {
        "label": "Legal & Reputational Risk",
        "color": "#b45309",
        "terms": {
            "lawsuit": 0.7, "sued": 0.7, "litigation": 0.65, "class action": 0.75,
            "settlement": 0.55, "breach of contract": 0.65, "negligence": 0.7,
            "misconduct": 0.75, "scandal": 0.8, "whistleblower": 0.7,
            "defamation": 0.6, "boycott": 0.65, "resigns amid": 0.7,
            "ousted": 0.65, "reputational": 0.6, "controversy": 0.6,
            "malpractice": 0.75, "conflict of interest": 0.7, "cover-up": 0.85,
            "wrongful": 0.65,
        },
    },
    "regulatory": {
        "label": "FINRA & Regulatory Bodies",
        "color": "#0e7490",
        "terms": {
            "finra": 0.9, "sec charges": 0.9, "sec fined": 0.9,
            "enforcement action": 0.85, "fined": 0.75, "fine": 0.6,
            "penalty": 0.7, "censure": 0.8, "cease and desist": 0.85,
            "disciplinary action": 0.8, "compliance failure": 0.8,
            "regulatory violation": 0.8, "disclosure violation": 0.8,
            "license revoked": 0.85, "barred": 0.8, "sanctioned by": 0.8,
            "audit failure": 0.75, "regulator": 0.6, "consent order": 0.8,
            "antitrust": 0.75, "probe": 0.7, "investigation": 0.65,
        },
    },
    "terrorism_serious_crime": {
        "label": "Terrorism & Serious Crime",
        "color": "#b91c1c",
        "terms": {
            "terrorism": 1.0, "terrorist financing": 1.0, "terrorist": 0.95,
            "extremism": 0.9, "extremist": 0.9, "organized crime": 0.95,
            "organised crime": 0.95, "drug trafficking": 0.95,
            "human trafficking": 1.0, "arms dealing": 0.95, "arms trafficking": 0.95,
            "smuggling": 0.85, "cartel": 0.9, "kidnapping": 0.9, "murder": 0.9,
            "indicted": 0.85, "convicted": 0.85, "criminal charges": 0.85,
            "narcotics": 0.85, "racketeering": 0.9, "modern slavery": 1.0,
            "forced labor": 0.95, "forced labour": 0.95,
        },
    },
    "sanctions": {
        "label": "Sanctions & Watchlists",
        "color": "#7c3aed",
        "terms": {
            "sanctions": 0.9, "sanctioned": 0.95, "ofac": 0.9, "sdn list": 0.95,
            "embargo": 0.85, "export control": 0.8, "watchlist": 0.85,
            "blocked entity": 0.9, "designated": 0.75, "asset freeze": 0.9,
            "frozen assets": 0.85, "sanctions evasion": 1.0,
            "politically exposed": 0.7, "blacklisted": 0.85,
            "restricted party": 0.8, "denied party": 0.8,
        },
    },
}

# Terms sent to GDELT's search API. A curated subset: the full term list
# produces a query long enough to be rejected. Tagging uses the whole taxonomy.
SEARCH_TERMS = [
    "fraud", "corruption", "bribery", "lawsuit", "investigation",
    "sanctions", "money laundering", "indictment", "settlement",
    "penalty", "misconduct", "terrorism", "trafficking",
]

# Order the dashboard presents the categories in.
CATEGORY_ORDER = [
    "financial_crime", "legal_reputational", "regulatory",
    "terrorism_serious_crime", "sanctions",
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
                "color": spec["color"],
                "severity": max(spec["terms"][term] for term in hits),
                "matched_terms": sorted(hits, key=len, reverse=True)[:4],
            }
        )

    tagged.sort(key=lambda c: c["severity"], reverse=True)
    return tagged


def category_labels() -> list[dict]:
    return [
        {"key": key, "label": RISK_TAXONOMY[key]["label"],
         "color": RISK_TAXONOMY[key]["color"]}
        for key in CATEGORY_ORDER
    ]
