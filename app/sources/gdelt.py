"""GDELT - global adverse media.

Searches the GDELT 2.0 Document API for the company name co-occurring with risk
vocabulary, then tags each headline against the risk taxonomy so the dashboard
can filter by risk type rather than treating all bad news alike.
"""

from __future__ import annotations

import logging
import re

from app.config import settings
from app.http_client import fetch_json
from app.resolution.normalize import name_tokens
from app.risk.taxonomy import SEARCH_TERMS, categories_for

log = logging.getLogger(__name__)

DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"

_SPLIT = re.compile(r"[^\w]+")

# Automated market-data wire copy. In these the bank or broker is the analyst
# issuing a rating, not the subject of an allegation - "Price Target Cut to
# $80.00 by Wells Fargo" is not adverse media about Wells Fargo. This is the
# single largest source of false positives for financial-sector names.
_MARKET_NOISE = re.compile(
    r"price target|target price|stock rating|rating (?:reiterated|lowered|raised|cut)"
    r"|shares (?:sold|bought|purchased|acquired) by"
    # "Position Boosted" and "Boosted Position" both occur in wire copy.
    r"|(?:stake|position|holdings) (?:boosted|lowered|trimmed|raised|increased|reduced|in)"
    r"|(?:boosted|lowered|trimmed|raised|increased|reduced|acquires|sells) (?:its |their )?"
    r"(?:stake|position|holdings|shares)"
    r"|short interest|eps estimate|earnings estimate|analysts?[' ]?s? (?:expect|forecast)"
    r"|\b(?:nyse|nasdaq|otcmkts|lse)\s*:|buy rating|sell rating|hold rating"
    r"|equities analysts|research analysts|price objective",
    re.I,
)


def _build_query(name: str) -> str:
    risk = " OR ".join(
        f'"{term}"' if " " in term else term for term in SEARCH_TERMS
    )
    return f'"{name}" ({risk})'


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


async def search(name: str, max_records: int = 75) -> list[dict]:
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

        if _MARKET_NOISE.search(title):
            continue

        # Require every token of the company name in the headline. GDELT's
        # full-text matching is loose, and a partial hit ("Apple" from
        # "Apple Hospitality") is the main source of false adverse media.
        relevance = _mentions_company(title, name)
        if relevance < 1.0:
            continue

        categories = categories_for(title)
        if not categories:
            continue  # matched the query but carries no taggable risk term

        severity = max(c["severity"] for c in categories)
        results.append(
            {
                "title": title,
                "source": article.get("domain") or "GDELT",
                "url": article.get("url"),
                "date": _format_date(article.get("seendate")),
                "language": article.get("language"),
                "source_country": article.get("sourcecountry"),
                "sentiment": "negative",
                "severity": round(severity, 2),
                "categories": categories,
                "category_keys": [c["key"] for c in categories],
                "matched_terms": sorted(
                    {t for c in categories for t in c["matched_terms"]}
                ),
                # Confidence that this article really concerns the supplier.
                "confidence": round(min(0.98, 0.55 + 0.4 * relevance), 4),
            }
        )

    results.sort(key=lambda a: (a["severity"], a["confidence"]), reverse=True)
    return results[:40]
