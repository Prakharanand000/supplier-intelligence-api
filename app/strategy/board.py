"""Strategy board - an autonomous executive decision board.

Ported from the CrewAI "StrategyOS" flow. Takes one high-stakes business
question ("Should Salesforce acquire Notion?") and returns a board-ready
GO / NO-GO / MORE INFORMATION REQUIRED verdict with a calibrated confidence
score, per-seat risk and conviction scores, a ranked adversarial review, and an
evidence audit - all as structured data the UI renders as tables and charts,
never a wall of prose.

The original flow chains six LLM+web-search stages (frame -> five specialist
seats + synthesis -> adversarial review -> evidence audit -> board vote). Here
the whole board runs as one Claude structured-output call, so the app returns a
single typed object. With no ANTHROPIC_API_KEY the endpoint serves curated
sample decisions instead, exactly as the risk side ships offline demo subjects.
"""

from __future__ import annotations

import json
import logging

from app.agent.investigator import _get_client
from app.config import settings
from app.strategy import samples as _samples

log = logging.getLogger(__name__)

# The five specialist seats the Chief of Staff can staff, with the flow's role
# titles and a UI icon key.
SEATS: list[dict] = [
    {"key": "Market", "role": "Head of Market Intelligence", "icon": "market"},
    {"key": "Finance", "role": "Head of Corporate Finance", "icon": "finance"},
    {"key": "Technology", "role": "Chief Architect", "icon": "tech"},
    {"key": "Competition", "role": "Competitive Strategy Lead", "icon": "competition"},
    {"key": "Legal", "role": "General Counsel's Office", "icon": "legal"},
]

BOARD_MEMBERS = ["CEO", "CFO", "CTO", "General Counsel"]

RISK_LEVELS = ["LOW", "MEDIUM", "HIGH"]
DECISIONS = ["GO", "NO-GO", "MORE INFORMATION REQUIRED"]
VOTES = ["GO", "NO-GO", "MORE INFORMATION REQUIRED", "CONDITIONAL GO"]
CLAIM_VERDICTS = ["VERIFIED", "WEAK", "SPECULATION", "UNSUPPORTED"]

# --------------------------------------------------------------------------
# Structured-output schema (Claude json_schema)
# --------------------------------------------------------------------------
STRATEGY_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "decision_type", "stakes", "success_criteria", "verdict",
        "seats", "attacks", "kill_shot", "evidence_audit", "board_vote",
        "conditions",
    ],
    "properties": {
        "decision_type": {
            "type": "string",
            "enum": ["acquisition", "market expansion", "pricing",
                     "product launch", "partnership"],
        },
        "stakes": {"type": "string"},
        "success_criteria": {
            "type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3,
        },
        "verdict": {
            "type": "object",
            "additionalProperties": False,
            "required": ["decision", "confidence", "strategic_fit",
                         "financial_risk", "regulatory_risk", "execution_risk",
                         "chair_summary"],
            "properties": {
                "decision": {"type": "string", "enum": DECISIONS},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                "strategic_fit": {"type": "integer", "minimum": 0, "maximum": 10},
                "financial_risk": {"type": "string", "enum": RISK_LEVELS},
                "regulatory_risk": {"type": "string", "enum": RISK_LEVELS},
                "execution_risk": {"type": "string", "enum": RISK_LEVELS},
                "chair_summary": {"type": "string"},
            },
        },
        "seats": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["seat", "staffed", "headline", "risk_score",
                             "conviction", "opportunities", "risks"],
                "properties": {
                    "seat": {"type": "string",
                             "enum": [s["key"] for s in SEATS]},
                    "staffed": {"type": "boolean"},
                    "bench_reason": {"type": "string"},
                    "headline": {"type": "string"},
                    "risk_score": {"type": "integer", "minimum": 0, "maximum": 10},
                    "conviction": {"type": "integer", "minimum": 0, "maximum": 10},
                    "opportunities": {"type": "array", "items": {"type": "string"}},
                    "risks": {"type": "array", "items": {"type": "string"}},
                    "claims": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["claim", "figure", "source"],
                            "properties": {
                                "claim": {"type": "string"},
                                "figure": {"type": "string"},
                                "source": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
        "attacks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["severity", "deal_breaker", "target_seat",
                             "claim_attacked", "why_it_breaks"],
                "properties": {
                    "severity": {"type": "integer", "minimum": 0, "maximum": 10},
                    "deal_breaker": {"type": "boolean"},
                    "target_seat": {"type": "string"},
                    "claim_attacked": {"type": "string"},
                    "why_it_breaks": {"type": "string"},
                },
            },
        },
        "kill_shot": {"type": "string"},
        "would_change_mind": {"type": "string"},
        "evidence_audit": {
            "type": "object",
            "additionalProperties": False,
            "required": ["verified_pct", "unsupported_pct", "integrity_note",
                         "audited_claims"],
            "properties": {
                "verified_pct": {"type": "integer", "minimum": 0, "maximum": 100},
                "weak_pct": {"type": "integer", "minimum": 0, "maximum": 100},
                "speculation_pct": {"type": "integer", "minimum": 0, "maximum": 100},
                "unsupported_pct": {"type": "integer", "minimum": 0, "maximum": 100},
                "integrity_note": {"type": "string"},
                "audited_claims": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["verdict", "seat", "claim"],
                        "properties": {
                            "verdict": {"type": "string", "enum": CLAIM_VERDICTS},
                            "seat": {"type": "string"},
                            "claim": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                    },
                },
            },
        },
        "board_vote": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["member", "vote", "rationale"],
                "properties": {
                    "member": {"type": "string"},
                    "vote": {"type": "string", "enum": VOTES},
                    "rationale": {"type": "string"},
                },
            },
        },
        "conditions": {"type": "array", "items": {"type": "string"}},
    },
}

SYSTEM_PROMPT = """You are StrategyOS, an autonomous executive decision board \
that evaluates one high-stakes business question and returns a board-ready \
verdict.

Run the full board in one pass:
1. FRAME - classify the decision (acquisition, market expansion, pricing, \
product launch, partnership), state the stakes in one sentence, and write three \
success criteria that must be true in 24 months for this to have been correct.
2. STAFF & INVESTIGATE - for each of the five seats (Market, Finance, \
Technology, Competition, Legal) decide whether it is material. Staffed seats get \
a headline, a risk_score (0-10), a conviction (0-10), concrete opportunities and \
risks, and specific claims with figures. Bench any seat that adds noise with a \
one-line bench_reason and staffed=false.
3. ADVERSARIAL REVIEW - produce four to six attacks ordered by severity (0-10). \
Each names the target seat, the claim attacked, and the exact mechanism by which \
it fails. Mark deal_breaker=true only where one flaw should stop the decision on \
its own. Add the one-sentence kill_shot.
4. EVIDENCE AUDIT - grade the claim base: what percent is verified vs \
unsupported, plus a one-line integrity note and a per-claim verdict list.
5. BOARD VOTE - cast four votes in character (CEO weighs position over \
spreadsheet; CFO defaults to no and moves only on evidence; CTO knows every \
engineering estimate is optimistic; General Counsel attaches conditions rather \
than voting no out of caution). Resolve into DECISION (GO / NO-GO / MORE \
INFORMATION REQUIRED), a confidence calibrated against the evidence audit not \
the tone of the room, strategic_fit and the three risk ratings, deal \
conditions, and a three-sentence chair_summary.

Be specific and quantitative. Do not manufacture consensus. Every figure you \
cite must name a real, checkable source; where you are estimating, say so in the \
source field. Return only the structured object."""


def _samples_index() -> list[dict]:
    return _samples.list_samples()


def list_samples() -> list[dict]:
    """Lightweight cards for the sample picker."""
    return [
        {
            "id": s["id"],
            "question": s["question"],
            "decision": s["verdict"]["decision"],
            "confidence": s["verdict"]["confidence"],
            "decision_type": s["decision_type"],
        }
        for s in _samples.SAMPLES.values()
    ]


def get_sample(sample_id: str) -> dict:
    """Full curated decision for a sample id. Raises KeyError if unknown."""
    return _decorate(dict(_samples.SAMPLES[sample_id]))


def _decorate(decision: dict) -> dict:
    """Attach static seat/member metadata and normalise ordering so the client
    renders consistently regardless of the order the model emitted."""
    decision.setdefault("seats", [])
    role_by_seat = {s["key"]: s for s in SEATS}
    # Keep seats in the board's canonical order; fold in role + icon.
    ordered = []
    by_key = {row.get("seat"): row for row in decision["seats"]}
    for meta in SEATS:
        row = by_key.get(meta["key"])
        if row is None:
            row = {"seat": meta["key"], "staffed": False,
                   "bench_reason": "Not addressed by the board.",
                   "headline": "", "risk_score": 0, "conviction": 0,
                   "opportunities": [], "risks": []}
        row["role"] = meta["role"]
        row["icon"] = meta["icon"]
        ordered.append(row)
    decision["seats"] = ordered
    decision["attacks"] = sorted(
        decision.get("attacks", []),
        key=lambda a: (a.get("deal_breaker", False), a.get("severity", 0)),
        reverse=True,
    )
    decision.setdefault("meta", {})
    decision["meta"]["seats"] = SEATS
    decision["meta"]["board_members"] = BOARD_MEMBERS
    return decision


async def decide(question: str) -> dict:
    """Run the decision board for `question`.

    With an ANTHROPIC_API_KEY the full board runs live via Claude structured
    output. Without one, a matching curated sample is returned, or a clear
    keyless notice if the question is not a known sample.
    """
    question = (question or "").strip()
    client = _get_client()

    if client is None:
        match = _samples.match(question)
        if match is not None:
            out = get_sample(match)
            out["generated_by"] = "curated sample (no ANTHROPIC_API_KEY)"
            out["question"] = question or out["question"]
            return out
        return _keyless_notice(question)

    user_message = (
        f"Evaluate this executive decision and return the board verdict:\n\n"
        f"{question}"
    )
    try:
        response = await client.messages.create(
            model=settings.claude_model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            output_config={
                "effort": settings.claude_effort,
                "format": {"type": "json_schema", "schema": STRATEGY_SCHEMA},
            },
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as exc:  # noqa: BLE001 - never 500 the endpoint on the LLM
        log.warning("strategy board generation failed: %s", exc)
        return _keyless_notice(question, error=str(exc))

    if response.stop_reason == "refusal":
        return _keyless_notice(question, error="model refusal")

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        return _keyless_notice(question, error="empty response")
    try:
        decision = json.loads(text)
    except json.JSONDecodeError:
        return _keyless_notice(question, error="unparseable response")

    decision["question"] = question
    decision["generated_by"] = settings.claude_model
    decision["usage"] = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    return _decorate(decision)


def _keyless_notice(question: str, error: str | None = None) -> dict:
    """A structured, renderable 'no live board available' object."""
    return {
        "question": question,
        "available": False,
        "generated_by": "unavailable",
        "notice": (
            "The live decision board needs an LLM key (ANTHROPIC_API_KEY). "
            "Pick one of the sample decisions to see the full board, or set a "
            "key to run this question live."
        ),
        "error": error,
        "samples": list_samples(),
    }
