"""GLEIF - global legal entity identity and ownership.

Gives the authoritative legal name, jurisdiction, registered address and the
LEI-to-LEI parent relationships that expose ownership structure.
"""

from __future__ import annotations

import logging

from app.http_client import fetch_json
from app.resolution.engine import EntityRecord

log = logging.getLogger(__name__)

BASE = "https://api.gleif.org/api/v1"
SEARCH_URL = f"{BASE}/lei-records"


def _address_text(block: dict | None) -> tuple[str | None, str | None, str | None]:
    if not block:
        return None, None, None
    lines = [line for line in (block.get("addressLines") or []) if line]
    city = block.get("city")
    country = block.get("country")
    parts = lines + [p for p in (city, block.get("postalCode")) if p]
    return (", ".join(parts) or None), city, country


async def _relation(lei: str, kind: str) -> dict | None:
    """kind is 'direct-parent' or 'ultimate-parent'. 404 simply means none."""
    data = await fetch_json(
        f"{SEARCH_URL}/{lei}/{kind}", ttl_hours=168, retries=2, expect_missing=True
    )
    if not isinstance(data, dict):
        return None
    node = data.get("data")
    if not isinstance(node, dict):
        return None
    entity = (node.get("attributes") or {}).get("entity") or {}
    name = (entity.get("legalName") or {}).get("name")
    if not name:
        return None
    return {
        "name": name,
        "lei": node.get("id"),
        "jurisdiction": entity.get("jurisdiction"),
        "relationship": kind.replace("-", "_"),
    }


async def search(
    name: str, country: str | None = None, limit: int = 8
) -> list[EntityRecord]:
    params = {"filter[fulltext]": name, "page[size]": str(limit)}
    data = await fetch_json(SEARCH_URL, params=params, ttl_hours=24)
    if not isinstance(data, dict):
        return []

    records: list[EntityRecord] = []
    for node in data.get("data") or []:
        attrs = node.get("attributes") or {}
        entity = attrs.get("entity") or {}
        legal_name = (entity.get("legalName") or {}).get("name")
        if not legal_name:
            continue

        lei = attrs.get("lei") or node.get("id")
        address, city, addr_country = _address_text(entity.get("legalAddress"))
        hq_address, hq_city, hq_country = _address_text(
            entity.get("headquartersAddress")
        )
        aliases = [
            other.get("name")
            for other in (entity.get("otherNames") or [])
            if other.get("name")
        ]

        parents = []
        if lei:
            for kind in ("direct-parent", "ultimate-parent"):
                rel = await _relation(lei, kind)
                if rel:
                    parents.append(rel)

        records.append(
            EntityRecord(
                source="GLEIF",
                source_id=lei,
                name=legal_name,
                aliases=aliases,
                country=addr_country or hq_country,
                city=city or hq_city,
                address=address or hq_address,
                officers=[],
                description=(entity.get("legalForm") or {}).get("id"),
                url=f"https://search.gleif.org/#/record/{lei}" if lei else None,
                raw={
                    "lei": lei,
                    "status": entity.get("status"),
                    "registration_status": (attrs.get("registration") or {}).get(
                        "status"
                    ),
                    "jurisdiction": entity.get("jurisdiction"),
                    "legal_form": (entity.get("legalForm") or {}).get("id"),
                    "category": entity.get("category"),
                    "registered_as": entity.get("registeredAs"),
                    "legal_address": address,
                    "headquarters_address": hq_address,
                    "parents": parents,
                },
            )
        )

    return records
