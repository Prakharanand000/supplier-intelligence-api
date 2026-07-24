"""AI insight for a single graph connection or node.

When an analyst clicks a specific relationship in the network, this asks Claude
to explain that connection and why it matters for third-party risk - grounded
strictly in the facts passed to it, never invented. Without an API key it falls
back to a deterministic explanation composed from the same facts, so the feature
works either way.
"""

from __future__ import annotations

import logging

from app.agent.investigator import _get_client
from app.config import settings

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a third-party risk analyst inspecting one edge of an
entity network graph. Explain this specific connection and why it matters for
risk. Use ONLY the facts supplied - do not invent people, companies, amounts,
dates, or allegations. If the facts do not establish a risk, say the connection
looks benign. Be concrete and concise: 2-4 sentences, no preamble."""


def _fallback(payload: dict) -> str:
    kind = payload.get("kind", "edge")
    subject = payload.get("subject") or "the subject"

    if kind == "node":
        label = payload.get("node_label", "This entity")
        detail = payload.get("node_detail") or payload.get("node_type", "")
        return (
            f"{label} ({detail}) appears in {subject}'s network. Review its own "
            f"filings and adverse-media exposure before relying on the link; a "
            f"connected party can carry risk that does not show up on {subject} "
            f"directly."
        )

    src = payload.get("source_label", "One party")
    tgt = payload.get("target_label", "another party")
    rel = payload.get("relationship") or "connected"
    conf = payload.get("confidence")
    desc = payload.get("description") or ""
    conf_txt = f" (confidence {conf:.2f})" if isinstance(conf, (int, float)) else ""
    tail = ""
    if payload.get("source_type") == "person" and payload.get("target_type") in ("entity", "company"):
        tail = (" A shared individual is a common vector for undisclosed conflicts "
                "of interest and for risk migrating between otherwise separate firms.")
    elif "parent" in rel.lower() or payload.get("target_type") == "holding":
        tail = (" Layered or offshore ownership can obscure ultimate control and "
                "warrants confirming the beneficial owner.")
    return f"{src} is linked to {tgt} as {rel}{conf_txt}. {desc}{tail}".strip()


def _build_prompt(payload: dict) -> str:
    lines = [f"Subject under investigation: {payload.get('subject', 'unknown')}",
             f"Subject risk level: {payload.get('risk_level', 'unknown')}", ""]
    if payload.get("kind") == "node":
        lines += [
            "Inspecting a NODE (entity or person):",
            f"- Label: {payload.get('node_label')}",
            f"- Type: {payload.get('node_type')}",
            f"- Detail: {payload.get('node_detail')}",
        ]
    else:
        lines += [
            "Inspecting a CONNECTION (graph edge) between two parties:",
            f"- From: {payload.get('source_label')} ({payload.get('source_type')})",
            f"- To: {payload.get('target_label')} ({payload.get('target_type')})",
            f"- Relationship: {payload.get('relationship')}",
            f"- Confidence: {payload.get('confidence')}",
            f"- Known facts: {payload.get('description')}",
        ]
    if payload.get("context"):
        lines += ["", f"Additional context: {payload['context']}"]
    return "\n".join(lines)


async def connection_insight(payload: dict) -> dict:
    client = _get_client()
    if client is None:
        return {"insight": _fallback(payload),
                "generated_by": "deterministic (no ANTHROPIC_API_KEY)"}

    try:
        response = await client.messages.create(
            model=settings.claude_model,
            max_tokens=600,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": _build_prompt(payload)}],
        )
    except Exception as exc:  # noqa: BLE001 - never fail the request on the LLM
        log.warning("connection insight generation failed: %s", exc)
        return {"insight": _fallback(payload),
                "generated_by": "deterministic (model error)"}

    if response.stop_reason == "refusal":
        return {"insight": _fallback(payload),
                "generated_by": "deterministic (model refusal)"}

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        return {"insight": _fallback(payload), "generated_by": "deterministic"}

    return {
        "insight": text.strip(),
        "generated_by": settings.claude_model,
        "usage": {"input_tokens": response.usage.input_tokens,
                  "output_tokens": response.usage.output_tokens},
    }
