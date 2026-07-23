"""AI investigation agent - turns retrieved evidence into an intelligence report.

Claude only summarizes and reasons over the evidence payload it is handed; it
never fetches anything and is instructed not to introduce outside facts. If no
API key is configured the report is composed deterministically from the same
evidence so the pipeline still returns a complete object.
"""

from __future__ import annotations

import json
import logging

from app.agent.prompts import REPORT_SCHEMA, SYSTEM_PROMPT
from app.config import settings

log = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None and settings.anthropic_api_key:
        from anthropic import AsyncAnthropic

        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def _build_payload(investigation: dict) -> str:
    """The evidence bundle handed to the model. Deliberately excludes the
    pre-computed narrative so Claude reasons from evidence, not from itself."""
    return json.dumps(
        {
            "query": investigation["query"],
            "supplier": investigation["supplier"],
            "entity_resolution": investigation["entity_resolution"],
            "ownership": investigation["ownership"],
            "sanctions": investigation["sanctions"],
            "litigation": investigation["litigation"],
            "adverse_media": investigation["adverse_media"],
            "risk": investigation["risk"],
            "evidence": investigation["evidence"],
            "sources_consulted": investigation["sources_consulted"],
        },
        indent=2,
        default=str,
    )


async def generate_report(investigation: dict) -> dict:
    client = _get_client()
    if client is None:
        log.info("No ANTHROPIC_API_KEY - generating deterministic report")
        return _fallback_report(investigation)

    payload = _build_payload(investigation)
    user_message = (
        "Investigate this supplier using only the evidence below.\n\n"
        f"```json\n{payload}\n```"
    )

    try:
        response = await client.messages.create(
            model=settings.claude_model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            output_config={
                "effort": settings.claude_effort,
                "format": {"type": "json_schema", "schema": REPORT_SCHEMA},
            },
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as exc:  # noqa: BLE001 - never fail the investigation on the LLM
        log.warning("Claude report generation failed: %s", exc)
        report = _fallback_report(investigation)
        report["generation_error"] = str(exc)
        return report

    if response.stop_reason == "refusal":
        log.warning("Claude declined to produce the report")
        report = _fallback_report(investigation)
        report["generation_error"] = "model refusal"
        return report

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        return _fallback_report(investigation)

    try:
        report = json.loads(text)
    except json.JSONDecodeError:
        log.warning("Claude returned unparseable JSON")
        return _fallback_report(investigation)

    report["generated_by"] = settings.claude_model
    report["usage"] = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    return report


# --------------------------------------------------------------------------
# Deterministic fallback
# --------------------------------------------------------------------------
def _cite(evidence: list[dict], source: str) -> str:
    ids = [e["id"] for e in evidence if e["source"] == source]
    return f" [{', '.join(ids[:3])}]" if ids else ""


def _fallback_report(investigation: dict) -> dict:
    supplier = investigation["supplier"]
    sanctions = investigation["sanctions"]
    litigation = investigation["litigation"]
    media = investigation["adverse_media"]
    ownership = investigation["ownership"]
    risk = investigation["risk"]
    evidence = investigation["evidence"]

    identity = (
        f"Resolved to '{supplier['name']}' with identity confidence "
        f"{supplier['identity_confidence']:.2f} ({supplier['status']})."
        + _cite(evidence, supplier.get("primary_source", "SEC"))
    )

    if ownership:
        owners = "; ".join(
            f"{o['name']} ({o.get('role') or o.get('relationship_type')})"
            for o in ownership[:5]
        )
        ownership_text = f"Related parties identified: {owners}." + _cite(
            evidence, "GLEIF"
        )
    else:
        ownership_text = "No evidence available for ownership or executives."

    if sanctions.get("match"):
        entity = sanctions.get("matched_entity") or {}
        sanctions_text = (
            f"OFAC SDN match against '{entity.get('name')}' "
            f"(similarity {sanctions.get('confidence', 0):.2f}, program "
            f"{entity.get('program')})." + _cite(evidence, "OFAC")
        )
    else:
        sanctions_text = (
            "No OFAC SDN match found against "
            f"{sanctions.get('list_size', 0)} screened names."
            + _cite(evidence, "OFAC")
        )

    cases = litigation.get("cases") or []
    if cases:
        litigation_text = (
            f"{len(cases)} federal docket(s) name this supplier, including "
            f"{cases[0]['case']}." + _cite(evidence, "CourtListener")
        )
    elif litigation.get("available"):
        litigation_text = "No matching federal dockets found."
    else:
        litigation_text = "No evidence available - litigation source unreachable."

    if media:
        media_text = (
            f"{len(media)} negative article(s) found. Most severe: "
            f"{media[0]['title']}." + _cite(evidence, "GDELT")
        )
    else:
        media_text = "No evidence available - no negative coverage matched."

    summary = " ".join(
        [identity, ownership_text, sanctions_text, litigation_text, media_text,
         f"Composite risk score {risk['score']}/100 ({risk['level']})."]
    )

    return {
        "summary": summary,
        "identity_assessment": identity,
        "ownership_assessment": ownership_text,
        "sanctions_assessment": sanctions_text,
        "litigation_assessment": litigation_text,
        "adverse_media_assessment": media_text,
        "key_findings": [
            {
                "finding": contribution["category"].replace("_", " ").title()
                + f" contributed {contribution['points']} points",
                "evidence_ids": [
                    e["id"] for e in evidence if e["source"] == contribution["source"]
                ][:3],
            }
            for contribution in risk["contributions"]
        ],
        "evidence_gaps": [
            f"{name} not consulted successfully"
            for name, ok in investigation["sources_consulted"].items()
            if not ok
        ],
        "recommendation": investigation["_recommendation"],
        "generated_by": "deterministic-fallback (no ANTHROPIC_API_KEY configured)",
    }
