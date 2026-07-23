"""Optional sources - mocked until credentials/paid access exist.

Both are clearly flagged `"mocked": true` in the response so an AI agent
consuming the intelligence object never mistakes them for live evidence.
"""

from __future__ import annotations

import hashlib

from app.resolution.normalize import normalize_domain


def opencorporates(name: str, country: str | None = None) -> dict:
    """MOCK. OpenCorporates registry lookup requires a paid API key."""
    return {
        "source": "OpenCorporates",
        "mocked": True,
        "reason": "API access requires a paid key",
        "query": {"name": name, "country": country},
        "registry_records": [
            {
                "name": name,
                "jurisdiction": (country or "unknown"),
                "company_number": None,
                "status": "unknown",
                "note": "Placeholder - not evidence. Do not cite.",
            }
        ],
    }


def virustotal(website: str | None) -> dict:
    """MOCK. Domain reputation requires a VirusTotal API key."""
    domain = normalize_domain(website)
    if not domain:
        return {
            "source": "VirusTotal",
            "mocked": True,
            "reason": "API key required",
            "domain": None,
            "verdict": "not_evaluated",
        }
    # Deterministic placeholder so demo output is stable across runs.
    digest = hashlib.sha256(domain.encode()).hexdigest()
    return {
        "source": "VirusTotal",
        "mocked": True,
        "reason": "API key required",
        "domain": domain,
        "verdict": "not_evaluated",
        "placeholder_hash": digest[:12],
        "note": "Placeholder - not evidence. Do not cite.",
    }
