"""SEC EDGAR - US company identity, filings and insider (Form 4) officers.

Every request carries the configured User-Agent contact string and is throttled
to well under SEC's 10 req/s ceiling by app.http_client. Responses are cached
in the database.
"""

from __future__ import annotations

import html
import logging
import re
from typing import Any

from app.http_client import fetch, fetch_json
from app.resolution.engine import EntityRecord
from app.resolution.normalize import normalize_name
from app.resolution.similarity import name_similarity

log = logging.getLogger(__name__)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
COMPANY_PAGE = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}"
)

_ticker_cache: list[dict] | None = None

# Reporting-owner fields inside a Form 4 XML document.
_RPT_OWNER = re.compile(r"<rptOwnerName>([^<]+)</rptOwnerName>")
_OFFICER_TITLE = re.compile(r"<officerTitle>([^<]+)</officerTitle>")
_IS_DIRECTOR = re.compile(r"<isDirector>\s*(1|true)\s*</isDirector>", re.I)
# EDGAR serves an XSL-rendered HTML view at xslF345X0N/<doc>; stripping the
# prefix yields the raw XML that actually carries the owner fields.
_XSL_PREFIX = re.compile(r"^xsl[^/]*/")


async def _load_tickers() -> list[dict]:
    """SEC's full registrant list, used as the name -> CIK lookup table."""
    global _ticker_cache
    if _ticker_cache is not None:
        return _ticker_cache

    data = await fetch_json(TICKERS_URL, ttl_hours=168)
    if not isinstance(data, dict):
        _ticker_cache = []
        return _ticker_cache

    entries = []
    for item in data.values():
        title = item.get("title")
        if not title:
            continue
        entries.append(
            {
                "cik": str(item.get("cik_str", "")).zfill(10),
                "ticker": item.get("ticker"),
                "title": title,
                "normalized": normalize_name(title),
            }
        )
    _ticker_cache = entries
    log.info("SEC: loaded %d registrants", len(entries))
    return entries


async def _find_ciks(name: str, limit: int = 5) -> list[dict]:
    entries = await _load_tickers()
    if not entries:
        return []

    normalized = normalize_name(name)
    tokens = set(normalized.split())
    if not tokens:
        return []

    # One registrant can appear under several tickers (common shares plus
    # preferred series), so keep the best-scoring row per CIK.
    best_by_cik: dict[str, tuple[float, dict]] = {}
    for entry in entries:
        if not tokens & set(entry["normalized"].split()):
            continue  # blocking: skip records with no shared token
        score = name_similarity(normalized, entry["normalized"])["score"]
        if score < 0.45:
            continue
        current = best_by_cik.get(entry["cik"])
        if current is None or score > current[0]:
            best_by_cik[entry["cik"]] = (score, entry)

    scored = sorted(best_by_cik.values(), key=lambda pair: pair[0], reverse=True)
    return [entry for _, entry in scored[:limit]]


async def _officers(
    cik: str, sub: dict, issuer_name: str, limit: int = 8, max_filings: int = 12
) -> list[dict[str, Any]]:
    """Executives and directors, read from recent Form 4 insider filings.

    Each Form 4 names one reporting owner plus their officer title / director
    flag, which is the most reliable public statement of who runs a US issuer.
    """
    recent = (sub.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accessions = recent.get("accessionNumber") or []
    documents = recent.get("primaryDocument") or []
    plain_cik = str(int(cik))

    people: dict[str, dict] = {}
    examined = 0

    for i, form in enumerate(forms):
        if form != "4" or i >= len(accessions) or i >= len(documents):
            continue
        if examined >= max_filings or len(people) >= limit:
            break
        examined += 1

        accession = accessions[i].replace("-", "")
        document = _XSL_PREFIX.sub("", documents[i] or "")
        if not document:
            continue

        url = (
            f"https://www.sec.gov/Archives/edgar/data/{plain_cik}/"
            f"{accession}/{document}"
        )
        body = await fetch(url, ttl_hours=168, retries=2)
        if not body:
            continue

        owner = _RPT_OWNER.search(body)
        if not owner:
            continue
        # XML entities (&amp;) must be decoded here, or they survive into the
        # report and get escaped a second time by the UI.
        name = html.unescape(owner.group(1)).strip()

        # `recent` also contains Form 4s this company filed as the reporting
        # owner of *another* issuer, where the owner is the company itself.
        # Those are not executives.
        if normalize_name(name) == normalize_name(issuer_name):
            continue

        key = name.lower()

        title_match = _OFFICER_TITLE.search(body)
        role = html.unescape(title_match.group(1)).strip() if title_match else None
        if not role and _IS_DIRECTOR.search(body):
            role = "Director"

        if key in people:
            people[key]["filings"] += 1
            people[key]["role"] = people[key]["role"] or role
            continue

        people[key] = {
            # EDGAR stores names uppercase for older filers.
            "name": name.title() if name.isupper() else name,
            "role": role or "Section 16 insider",
            "filings": 1,
            "source_url": url,
        }

    return list(people.values())


async def _submission(cik: str) -> dict | None:
    return await fetch_json(SUBMISSIONS_URL.format(cik=cik), ttl_hours=24)


# EDGAR reports a US filer's location as a bare state code with country=null,
# so "CA" must resolve to "United States" rather than being read as a country.
US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY", "PR", "VI", "GU", "AS", "MP",
}


def _address(sub: dict) -> tuple[str | None, str | None, str | None]:
    addresses = sub.get("addresses") or {}
    business = addresses.get("business") or addresses.get("mailing") or {}

    street = " ".join(
        part for part in (business.get("street1"), business.get("street2")) if part
    )
    city = business.get("city")

    state_or_country = (business.get("stateOrCountry") or "").strip().upper()
    if business.get("country"):
        country = business["country"]
    elif state_or_country in US_STATE_CODES:
        country = "United States"
    else:
        country = business.get("stateOrCountryDescription") or state_or_country or None

    parts = [street, city]
    if state_or_country:
        parts.append(state_or_country)
    parts.append(business.get("zipCode"))
    full = ", ".join(p for p in parts if p)
    return (full or None), city, country


def _recent_filings(sub: dict, limit: int = 8) -> list[dict]:
    recent = (sub.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accessions = recent.get("accessionNumber") or []
    dates = recent.get("filingDate") or []
    docs = recent.get("primaryDocument") or []
    descriptions = recent.get("primaryDocDescription") or []
    cik = str(sub.get("cik", "")).lstrip("0")

    out = []
    for i in range(min(len(forms), len(accessions), len(dates))):
        acc = accessions[i].replace("-", "")
        doc = docs[i] if i < len(docs) else ""
        out.append(
            {
                "form": forms[i],
                "filed": dates[i],
                "description": descriptions[i] if i < len(descriptions) else None,
                "url": (
                    f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
                    if doc
                    else f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}"
                ),
            }
        )
        if len(out) >= limit:
            break
    return out


async def search(name: str, country: str | None = None) -> list[EntityRecord]:
    """Return candidate SEC registrants for the query name."""
    matches = await _find_ciks(name)
    records: list[EntityRecord] = []

    for match in matches:
        sub = await _submission(match["cik"])
        if not sub:
            continue

        address, city, sub_country = _address(sub)
        former = [
            fn.get("name")
            for fn in (sub.get("formerNames") or [])
            if fn.get("name")
        ]
        tickers = sub.get("tickers") or []
        issuer_name = sub.get("name") or match["title"]
        officers = await _officers(match["cik"], sub, issuer_name)

        records.append(
            EntityRecord(
                source="SEC",
                source_id=match["cik"],
                name=sub.get("name") or match["title"],
                aliases=former,
                country=sub_country,
                city=city,
                address=address,
                website=sub.get("website") or None,
                officers=[o["name"] for o in officers],
                description=sub.get("sicDescription"),
                url=COMPANY_PAGE.format(cik=match["cik"]),
                raw={
                    "cik": match["cik"],
                    "tickers": tickers,
                    "exchanges": sub.get("exchanges") or [],
                    "sic": sub.get("sic"),
                    "sic_description": sub.get("sicDescription"),
                    "entity_type": sub.get("entityType"),
                    "state_of_incorporation": sub.get("stateOfIncorporationDescription"),
                    "ein": sub.get("ein"),
                    "phone": sub.get("phone"),
                    "former_names": former,
                    "officers": officers,
                    "recent_filings": _recent_filings(sub),
                },
            )
        )

    return records
