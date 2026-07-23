"""Explainable, rule-based risk scoring.

No ML model. Every point in the score traces to a named rule and a piece of
evidence, so the output can be audited by a human and defended to a regulator.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Base weights from the product spec.
WEIGHT_SANCTIONS = 100
WEIGHT_LITIGATION = 30
WEIGHT_ADVERSE_MEDIA = 20
WEIGHT_IDENTITY = 25
WEIGHT_OWNERSHIP = 15

LEVEL_BANDS = [(80, "critical"), (55, "high"), (30, "medium"), (0, "low")]


@dataclass
class Signal:
    category: str
    description: str
    severity: int
    source: str
    confidence: float
    evidence_urls: list[str] = field(default_factory=list)


def _level(score: int) -> str:
    for floor, label in LEVEL_BANDS:
        if score >= floor:
            return label
    return "low"


def evaluate(
    *,
    sanctions: dict,
    litigation: dict,
    adverse_media: list[dict],
    identity_confidence: float,
    identity_verdict: str,
    ownership: list[dict],
    sources_consulted: dict[str, bool],
) -> tuple[dict, list[Signal]]:
    """Return (risk_block, signals)."""
    signals: list[Signal] = []

    # --- Sanctions ---------------------------------------------------------
    if sanctions.get("match"):
        entity = sanctions.get("matched_entity") or {}
        confidence = float(sanctions.get("confidence", 0.0))
        # A "possible" match scores lower than a confirmed one, but never zero.
        severity = int(round(WEIGHT_SANCTIONS * max(0.6, confidence)))
        signals.append(
            Signal(
                category="sanctions",
                description=(
                    f"OFAC SDN name match: '{entity.get('name')}' "
                    f"(program {entity.get('program') or 'unknown'}, "
                    f"similarity {confidence:.2f})"
                ),
                severity=severity,
                source="OFAC",
                confidence=confidence,
            )
        )
    elif not sources_consulted.get("ofac", False):
        signals.append(
            Signal(
                category="coverage_gap",
                description="OFAC list could not be loaded; sanctions status unverified",
                severity=WEIGHT_IDENTITY,
                source="OFAC",
                confidence=0.5,
            )
        )

    # --- Litigation --------------------------------------------------------
    cases = litigation.get("cases") or []
    if cases:
        top = cases[: min(3, len(cases))]
        # Flat weight, deliberately not scaled by case count: docket volume
        # tracks company size more than company risk, so counting it twice
        # would push every large supplier into the top band. The count stays
        # visible in the description and evidence for a human to weigh.
        signals.append(
            Signal(
                category="litigation",
                description=(
                    f"{len(cases)} federal docket(s) naming the supplier, "
                    f"including {top[0]['case']}"
                ),
                severity=WEIGHT_LITIGATION,
                source="CourtListener",
                confidence=max(c["confidence"] for c in cases),
                evidence_urls=[c["url"] for c in top if c.get("url")],
            )
        )
    elif not litigation.get("available", False):
        signals.append(
            Signal(
                category="coverage_gap",
                description=(
                    "Litigation records unavailable (CourtListener not reachable "
                    "or no API token configured)"
                ),
                severity=10,
                source="CourtListener",
                confidence=0.5,
            )
        )

    # --- Adverse media -----------------------------------------------------
    if adverse_media:
        # Scaled by the severity of the worst allegation, not by article count:
        # one indictment matters more than twenty reprints of a settlement.
        peak = max(a["severity"] for a in adverse_media)
        severity = int(round(WEIGHT_ADVERSE_MEDIA * peak))
        signals.append(
            Signal(
                category="adverse_media",
                description=(
                    f"{len(adverse_media)} negative article(s) in the last "
                    f"24 months; most severe: {adverse_media[0]['title'][:140]}"
                ),
                severity=severity,
                source="GDELT",
                confidence=max(a["confidence"] for a in adverse_media),
                evidence_urls=[a["url"] for a in adverse_media[:3] if a.get("url")],
            )
        )

    # --- Identity ----------------------------------------------------------
    if identity_verdict != "verified":
        # Scale the penalty by how far short of verification we fell.
        shortfall = max(0.0, 1.0 - identity_confidence)
        signals.append(
            Signal(
                category="identity",
                description=(
                    f"Supplier identity is {identity_verdict} "
                    f"(resolution confidence {identity_confidence:.2f}); "
                    "no authoritative registry record matched with confidence"
                ),
                severity=int(round(WEIGHT_IDENTITY * shortfall)) or 5,
                source="EntityResolution",
                confidence=round(1.0 - identity_confidence, 4),
            )
        )

    # --- Ownership complexity ---------------------------------------------
    parents = [o for o in ownership if o.get("relationship_type") in
               ("direct_parent", "ultimate_parent")]
    distinct_jurisdictions = {
        o.get("country") for o in ownership if o.get("country")
    }
    if len(parents) >= 2 or len(distinct_jurisdictions) > 1:
        signals.append(
            Signal(
                category="ownership_complexity",
                description=(
                    f"Multi-layer ownership: {len(parents)} parent entit(ies) "
                    f"across {len(distinct_jurisdictions) or 1} jurisdiction(s)"
                ),
                severity=WEIGHT_OWNERSHIP,
                source="GLEIF",
                confidence=0.8,
            )
        )

    # --- Aggregate ---------------------------------------------------------
    raw = sum(s.severity for s in signals)
    score = max(0, min(100, raw))
    level = _level(score)

    risk = {
        "score": score,
        "raw_score": raw,
        "level": level,
        "reasons": [s.description for s in signals],
        "contributions": [
            {
                "category": s.category,
                "points": s.severity,
                "source": s.source,
                "confidence": s.confidence,
            }
            for s in sorted(signals, key=lambda s: s.severity, reverse=True)
        ],
        "rules_applied": {
            "sanctions_match": WEIGHT_SANCTIONS,
            "litigation_found": WEIGHT_LITIGATION,
            "adverse_media": WEIGHT_ADVERSE_MEDIA,
            "identity_unverified": WEIGHT_IDENTITY,
            "ownership_complexity": WEIGHT_OWNERSHIP,
        },
    }
    return risk, signals


def recommendation(risk: dict) -> str:
    return {
        "critical": "Do not onboard. Escalate to compliance immediately.",
        "high": "Block pending enhanced due diligence and compliance sign-off.",
        "medium": "Enhanced review recommended before onboarding.",
        "low": "Standard onboarding may proceed with periodic monitoring.",
    }[risk["level"]]
