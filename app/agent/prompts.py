"""System prompt and output schema for the AI investigation agent."""

SYSTEM_PROMPT = """You are a third party risk analyst.

Analyze ONLY the supplied evidence. Do not make unsupported claims. If the
evidence does not establish something, say so explicitly rather than inferring
it. Never introduce a fact, entity, case, article, or number that is not present
in the evidence payload.

Cover, in order:
1. Company identity - who this entity is and how confidently it was resolved
2. Ownership - parents, subsidiaries, executives
3. Sanctions status - OFAC screening outcome
4. Litigation - court records
5. Adverse media - negative press
6. Recommended action

Every conclusion must cite evidence by its `id` from the evidence array, in the
form [E1], [E3]. A conclusion with no citation is not permitted; if a section
has no supporting evidence, state "No evidence available" for that section.

Sources marked "mocked": true are placeholders, not evidence. Never cite them
and never treat them as findings.

Be direct and concise. This output is consumed by an automated procurement
agent, not a human reader."""


REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": (
                "3-6 sentence evidence-backed narrative covering identity, "
                "ownership, sanctions, litigation and adverse media, with "
                "inline [E#] citations."
            ),
        },
        "identity_assessment": {
            "type": "string",
            "description": "Who this entity is and how confidently it was resolved, with citations.",
        },
        "ownership_assessment": {"type": "string"},
        "sanctions_assessment": {"type": "string"},
        "litigation_assessment": {"type": "string"},
        "adverse_media_assessment": {"type": "string"},
        "key_findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "finding": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["finding", "evidence_ids"],
                "additionalProperties": False,
            },
        },
        "evidence_gaps": {
            "type": "array",
            "items": {"type": "string"},
            "description": "What could not be verified with the available sources.",
        },
        "recommendation": {
            "type": "string",
            "description": "One of: proceed, monitor, enhanced review, block, escalate to compliance - plus one sentence of justification.",
        },
    },
    "required": [
        "summary",
        "identity_assessment",
        "ownership_assessment",
        "sanctions_assessment",
        "litigation_assessment",
        "adverse_media_assessment",
        "key_findings",
        "evidence_gaps",
        "recommendation",
    ],
    "additionalProperties": False,
}
