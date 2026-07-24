"""SEC EDGAR - US company identity, filings and insider (Form 4) officers.

Every request carries the configured User-Agent contact string and is throttled
to well under SEC's 10 req/s ceiling by app.http_client. Responses are cached
in the database.
"""

from __future__ import annotations

import html
import logging
import re
import xml.etree.ElementTree as ET
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

# Fallback for Form 4 documents that will not parse as XML.
_RPT_OWNER = re.compile(r"<rptOwnerName>([^<]+)</rptOwnerName>")
_OFFICER_TITLE = re.compile(r"<officerTitle>([^<]+)</officerTitle>")
_IS_DIRECTOR = re.compile(r"<isDirector>\s*(1|true)\s*</isDirector>", re.I)
# EDGAR serves an XSL-rendered HTML view at xslF345X0N/<doc>; stripping the
# prefix yields the raw XML that actually carries the owner fields.
_XSL_PREFIX = re.compile(r"^xsl[^/]*/")

# Form 4 transaction codes. P/S are open-market trades and carry the most
# signal; A/M/F are compensation mechanics.
TRANSACTION_CODES = {
    "P": "Open-market purchase",
    "S": "Open-market sale",
    "A": "Grant or award",
    "M": "Option exercise",
    "X": "Option exercise",
    "F": "Shares withheld for tax",
    "G": "Gift",
    "D": "Disposition to issuer",
    "C": "Conversion",
    "J": "Other acquisition or disposition",
}


def _text(node: ET.Element | None, path: str) -> str | None:
    """Form 4 wraps most scalars in a <value> child."""
    if node is None:
        return None
    found = node.find(path)
    if found is None:
        return None
    value = found.findtext("value")
    if value is None:
        value = found.text
    return value.strip() if value else None


def _to_float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _regex_fallback(body: str) -> dict | None:
    """Recover the owner from a document the XML path could not read.

    Covers both the XSL-rendered HTML view (not well-formed XML) and
    well-formed documents that simply lack the expected elements.
    """
    owner = _RPT_OWNER.search(body)
    if not owner:
        return None
    title = _OFFICER_TITLE.search(body)
    return {
        "owner": html.unescape(owner.group(1)).strip(),
        "role": html.unescape(title.group(1)).strip() if title else None,
        "is_director": bool(_IS_DIRECTOR.search(body)),
        "transactions": [],
    }


def _parse_form4(body: str) -> dict | None:
    """Extract the reporting owner, their role, and their transactions."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return _regex_fallback(body)

    owner = root.findtext(".//reportingOwnerId/rptOwnerName")
    if not owner:
        # Parsed cleanly but is not a Form 4 shape we recognise.
        return _regex_fallback(body)

    relationship = root.find(".//reportingOwnerRelationship")
    role = None
    is_director = False
    if relationship is not None:
        role = (relationship.findtext("officerTitle") or "").strip() or None
        is_director = (relationship.findtext("isDirector") or "").strip() in (
            "1", "true", "Y",
        )

    transactions: list[dict] = []
    for node in root.findall(".//nonDerivativeTransaction"):
        amounts = node.find("transactionAmounts")
        shares = _to_float(_text(amounts, "transactionShares"))
        price = _to_float(_text(amounts, "transactionPricePerShare"))
        disposed = (_text(amounts, "transactionAcquiredDisposedCode") or "").upper()
        code = (
            node.findtext("transactionCoding/transactionCode") or ""
        ).strip().upper()
        date = _text(node, "transactionDate")

        if shares is None or not date:
            continue

        transactions.append(
            {
                "date": date,
                "security": _text(node, "securityTitle"),
                "code": code,
                "code_label": TRANSACTION_CODES.get(code, code or "Unspecified"),
                "direction": "acquired" if disposed == "A" else "disposed",
                "shares": shares,
                "price_per_share": price,
                "value": round(shares * price, 2) if price else None,
            }
        )

    return {
        "owner": owner.strip(),
        "role": role,
        "is_director": is_director,
        "transactions": transactions,
    }


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


async def _insiders(
    cik: str, sub: dict, issuer_name: str, limit: int = 10, max_filings: int = 18
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Executives, directors and their filed transactions, from Form 4s.

    Each Form 4 names one reporting owner plus their officer title / director
    flag - the most reliable public statement of who runs a US issuer - and
    the securities transactions they reported, which is real transaction data
    rather than an inferred relationship.

    Returns (people, transactions).
    """
    recent = (sub.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accessions = recent.get("accessionNumber") or []
    documents = recent.get("primaryDocument") or []
    plain_cik = str(int(cik))

    people: dict[str, dict] = {}
    transactions: list[dict] = []
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

        parsed = _parse_form4(body)
        if not parsed:
            continue

        # XML entities (&amp;) must be decoded here, or they survive into the
        # report and get escaped a second time by the UI.
        name = html.unescape(parsed["owner"]).strip()

        # `recent` also contains Form 4s this company filed as the reporting
        # owner of *another* issuer, where the owner is the company itself.
        # Those are not executives.
        if normalize_name(name) == normalize_name(issuer_name):
            continue

        role = html.unescape(parsed["role"]).strip() if parsed["role"] else None
        if not role and parsed["is_director"]:
            role = "Director"

        for txn in parsed["transactions"]:
            txn["insider"] = name.title() if name.isupper() else name
            txn["filing_url"] = url
            transactions.append(txn)

        key = name.lower()
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

    return list(people.values()), transactions


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

    for rank, match in enumerate(matches):
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

        # Form 4s are one HTTP request each, so only the strongest candidates
        # earn a deep insider pull. Weak candidates still get enough to
        # corroborate identity across sources.
        if rank == 0:
            officers, transactions = await _insiders(
                match["cik"], sub, issuer_name, limit=14, max_filings=30
            )
        elif rank < 3:
            officers, transactions = await _insiders(
                match["cik"], sub, issuer_name, limit=5, max_filings=6
            )
        else:
            officers, transactions = [], []

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
                    "transactions": transactions,
                    "recent_filings": _recent_filings(sub),
                },
            )
        )

    return records
