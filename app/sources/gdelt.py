"""GDELT - global adverse media.

Searches the GDELT 2.0 Document API for the company name co-occurring with
risk vocabulary, then scores each article's sentiment from the headline.
"""

from __future__ import annotations

import logging
import re

from app.config import settings
from app.http_client import fetch_json
from app.resolution.normalize import name_tokens

log = logging.getLogger(__name__)

DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"

RISK_TERMS = [
    "fraud", "corruption", "lawsuit", "investigation", "sanctions",
    "bribery", "money laundering", "indictment", "settlement", "penalty",
    "recall", "misconduct", "violation",
]

# Headline vocabulary -> severity weight. Used to grade each article rather
# than hand-labelling everything "negative".
SEVERITY_TERMS = {
    "indicted": 1.0, "indictment": 1.0, "fraud": 1.0, "bribery": 1.0,
    "money laundering": 1.0, "sanctioned": 1.0, "sanctions": 0.9,
    "corruption": 0.95, "convicted": 1.0, "guilty": 0.95,
    "criminal": 0.9, "raid": 0.85, "probe": 0.75, "investigation": 0.75,
    "lawsuit": 0.7, "sued": 0.7, "litigation": 0.7, "subpoena": 0.75,
    "penalty": 0.7, "fine": 0.65, "fined": 0.7, "settlement": 0.55,
    "violation": 0.7, "misconduct": 0.8, "recall": 0.6, "breach": 0.65,
    "whistleblower": 0.7, "class action": 0.7, "antitrust": 0.75,
}

_SPLIT = re.compile(r"[^\w]+")


def _build_query(name: str) -> str:
    risk = " OR ".join(f'"{term}"' if " " in term else term for term in RISK_TERMS)
    return f'"{name}" ({risk})'


def _score_article(title: str) -> tuple[str, float, list[str]]:
    lowered = (title or "").lower()
    hits = [term for term in SEVERITY_TERMS if term in lowered]
    if not hits:
        return "neutral", 0.0, []
    severity = max(SEVERITY_TERMS[t] for t in hits)
    return "negative", severity, hits


def _mentions_company(title: str, name: str) -> float:
    """How much of the company name actually appears in the headline.

    GDELT full-text search is loose; this keeps 'Apple' articles about fruit
    from being scored as adverse media on Apple Inc.
    """
    query_tokens = name_tokens(name)
    if not query_tokens:
        return 0.0
    title_tokens = {t for t in _SPLIT.split((title or "").lower()) if t}
    return len(query_tokens & title_tokens) / len(query_tokens)


def _format_date(seendate: str | None) -> str | None:
    if not seendate or len(seendate) < 8:
        return seendate
    return f"{seendate[0:4]}-{seendate[4:6]}-{seendate[6:8]}"


async def search(name: str, max_records: int = 50) -> list[dict]:
    params = {
        "query": _build_query(name),
        "mode": "artlist",
        "format": "json",
        "maxrecords": str(max_records),
        "timespan": f"{settings.gdelt_months}m",
        "sort": "hybridrel",
    }
    data = await fetch_json(DOC_API, params=params, ttl_hours=6)
    if not isinstance(data, dict):
        return []

    results: list[dict] = []
    seen_titles: set[str] = set()

    for article in data.get("articles") or []:
        title = (article.get("title") or "").strip()
        if not title:
            continue
        key = title.lower()[:120]
        if key in seen_titles:
            continue
        seen_titles.add(key)

        # Require every token of the company name in the headline. GDELT's
        # full-text matching is loose, and a partial hit ("Apple" from
        # "Apple Hospitality") is the main source of false adverse media.
        relevance = _mentions_company(title, name)
        if relevance < 1.0:
            continue

        sentiment, severity, matched_terms = _score_article(title)
        if sentiment != "negative":
            continue

        results.append(
            {
                "title": title,
                "source": article.get("domain") or "GDELT",
                "url": article.get("url"),
                "date": _format_date(article.get("seendate")),
                "language": article.get("language"),
                "source_country": article.get("sourcecountry"),
                "sentiment": sentiment,
                "severity": round(severity, 2),
                "matched_terms": matched_terms,
                # Confidence that this article really concerns the supplier.
                "confidence": round(min(0.98, 0.55 + 0.4 * relevance), 4),
            }
        )

    results.sort(key=lambda a: (a["severity"], a["confidence"]), reverse=True)
    return results[:20]
