"""CourtListener - US federal and state litigation.

The v4 search API is rate-limited for anonymous callers and generally needs a
free API token. Without one the source degrades to an explicit "unavailable"
rather than silently reporting zero litigation, so the risk engine can tell the
difference between "no cases" and "we could not look".
"""

from __future__ import annotations

import logging

from app.config import settings
from app.http_client import fetch_json
from app.resolution.normalize import name_tokens

log = logging.getLogger(__name__)

SEARCH_URL = "https://www.courtlistener.com/api/rest/v4/search/"


def _headers() -> dict[str, str]:
    if settings.courtlistener_api_token:
        return {"Authorization": f"Token {settings.courtlistener_api_token}"}
    return {}


def _relevance(text: str, name: str) -> float:
    query_tokens = name_tokens(name)
    if not query_tokens:
        return 0.0
    body_tokens = name_tokens(text)
    return len(query_tokens & body_tokens) / len(query_tokens)


async def search(name: str, limit: int = 10) -> dict:
    """Returns {'available': bool, 'cases': [...], 'note': str|None}."""
    params = {
        "q": f'"{name}"',
        "type": "r",  # RECAP: federal district and appellate dockets
        "order_by": "score desc",
    }
    data = await fetch_json(
        SEARCH_URL, params=params, headers=_headers(), ttl_hours=24, retries=2
    )

    if not isinstance(data, dict):
        return {
            "available": False,
            "cases": [],
            "note": (
                "CourtListener unavailable - set COURTLISTENER_API_TOKEN for "
                "litigation coverage"
            ),
        }

    cases: list[dict] = []
    for item in (data.get("results") or [])[: limit * 3]:
        case_name = item.get("caseName") or item.get("case_name") or ""
        if not case_name:
            continue
        party_text = " ".join(
            filter(None, [case_name, item.get("suitNature") or "", item.get("docketNumber") or ""])
        )
        relevance = _relevance(party_text, name)
        if relevance < 0.5:
            continue

        docket_id = item.get("docket_id") or item.get("id")
        cases.append(
            {
                "case": case_name,
                "court": item.get("court") or item.get("court_id"),
                "date": item.get("dateFiled") or item.get("dateArgued"),
                "docket_number": item.get("docketNumber"),
                "nature_of_suit": item.get("suitNature"),
                "url": (
                    f"https://www.courtlistener.com/docket/{docket_id}/"
                    if docket_id
                    else None
                ),
                "confidence": round(min(0.97, 0.55 + 0.4 * relevance), 4),
            }
        )
        if len(cases) >= limit:
            break

    return {"available": True, "cases": cases, "note": None}
