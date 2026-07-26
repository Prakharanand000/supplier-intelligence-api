"""Curated sample decisions for the strategy board.

These let the whole strategy tab run instantly with no LLM key, the same way
the risk side ships offline demo subjects. They are *illustrative scenario
analyses*, not sourced research: figures are labelled as estimates, and the
evidence audit reflects that honestly. Run a question live (with an
ANTHROPIC_API_KEY) to get sourced, web-checked analysis instead.
"""

from __future__ import annotations

EST = "Illustrative estimate (offline sample)"


SAMPLES: dict[str, dict] = {
    # -----------------------------------------------------------------------
    "salesforce_notion": {
        "id": "salesforce_notion",
        "question": "Should Salesforce acquire Notion?",
        "decision_type": "acquisition",
        "stakes": (
            "A ~$12-15B bet on owning the collaborative-docs surface, against a "
            "portfolio that already includes Slack and Quip."
        ),
        "success_criteria": [
            "Notion's ~$400M ARR keeps compounding above 40% inside Salesforce two years post-close.",
            "Net new Slack + Notion seats outpace the cannibalisation of Quip and standalone Notion churn.",
            "Integration ships a joint product within 12 months without a senior-IC exodus.",
        ],
        "verdict": {
            "decision": "NO-GO",
            "confidence": 68,
            "strategic_fit": 5,
            "financial_risk": "HIGH",
            "regulatory_risk": "LOW",
            "execution_risk": "HIGH",
            "chair_summary": (
                "No-go: the price implies a growth and synergy path the evidence "
                "does not support, and the capability already overlaps Slack and "
                "Quip. The strategic logic is real but better bought as a "
                "partnership than a $12B+ acquisition. A materially lower entry "
                "price or a credible Quip-retirement plan would reopen it."
            ),
        },
        "seats": [
            {
                "seat": "Market", "staffed": True,
                "headline": "Real demand, but Salesforce already owns two seats on this surface.",
                "risk_score": 6, "conviction": 6,
                "opportunities": [
                    "Notion sits with the SMB/prosumer segment Salesforce underserves",
                    "AI-notes momentum extends the Einstein surface",
                ],
                "risks": [
                    "Overlap with Slack canvas and Quip",
                    "Prosumer motion is alien to Salesforce's enterprise sales engine",
                ],
                "claims": [
                    {"claim": "Notion annual recurring revenue", "figure": "~$400M ARR", "source": EST},
                    {"claim": "Collaborative-docs TAM", "figure": "~$45B by 2027", "source": EST},
                ],
            },
            {
                "seat": "Finance", "staffed": True,
                "headline": "Entry multiple demands flawless execution the base rate does not grant.",
                "risk_score": 8, "conviction": 7,
                "opportunities": ["Cross-sell into 150k+ Salesforce accounts"],
                "risks": [
                    "~30x ARR entry multiple",
                    "Synergy case double-counts seats already paying for Slack",
                    "Same capital returns more via buyback at current FCF yield",
                ],
                "claims": [
                    {"claim": "Implied acquisition price", "figure": "$12-15B", "source": EST},
                    {"claim": "Entry multiple", "figure": "~30x ARR", "source": EST},
                ],
            },
            {
                "seat": "Technology", "staffed": True,
                "headline": "Two document engines and identity stacks; a joint product is 4-6 engineer-quarters.",
                "risk_score": 7, "conviction": 6,
                "opportunities": ["Notion's block model is a strong base for AI docs"],
                "risks": [
                    "Quip and Notion solve the same problem twice",
                    "Identity/permissions reconciliation across Slack, Quip, Notion",
                ],
                "claims": [
                    {"claim": "Integration effort to first joint product", "figure": "4-6 engineer-quarters", "source": EST},
                ],
            },
            {
                "seat": "Competition", "staffed": True,
                "headline": "Blocks Microsoft and Google from Notion, but they retaliate cheaply in-suite.",
                "risk_score": 5, "conviction": 5,
                "opportunities": ["Denies a fast-growing asset to Microsoft"],
                "risks": [
                    "Microsoft bundles Loop into M365 at zero marginal price",
                    "Google Workspace answers with Gemini-in-Docs",
                ],
                "claims": [
                    {"claim": "Notion registered users", "figure": "~100M", "source": EST},
                ],
            },
            {
                "seat": "Legal", "staffed": False,
                "bench_reason": "No antitrust choke point at this share; benched to keep signal high.",
                "headline": "", "risk_score": 2, "conviction": 4,
                "opportunities": [], "risks": [],
            },
        ],
        "attacks": [
            {"severity": 9, "deal_breaker": True, "target_seat": "Finance",
             "claim_attacked": "cross-sell synergy justifies a 30x ARR multiple",
             "why_it_breaks": "The synergy model counts Slack seats that already exist as net-new Notion revenue, double-counting the same customer."},
            {"severity": 8, "deal_breaker": False, "target_seat": "Market",
             "claim_attacked": "Notion fills a segment Salesforce underserves",
             "why_it_breaks": "The prosumer bottoms-up motion is the opposite of Salesforce's top-down enterprise sales; every prior prosumer acquisition lost its motion inside 18 months."},
            {"severity": 7, "deal_breaker": False, "target_seat": "Technology",
             "claim_attacked": "a joint product ships in 12 months",
             "why_it_breaks": "It requires retiring Quip, which has paying enterprise customers under contract - a political, not just technical, timeline."},
            {"severity": 6, "deal_breaker": False, "target_seat": "Competition",
             "claim_attacked": "acquiring Notion denies it to Microsoft",
             "why_it_breaks": "Microsoft answers with Loop at zero marginal price inside M365, so the denial buys a temporary lead, not durable advantage."},
            {"severity": 5, "deal_breaker": False, "target_seat": "Market",
             "claim_attacked": "40%+ growth persists post-close",
             "why_it_breaks": "Growth extrapolates the last strong quarter; founder-led products routinely decelerate on acquisition as key ICs vest and leave."},
        ],
        "kill_shot": "You are paying $12B to buy a third product that does what Slack and Quip already do, on a synergy math that counts the same customer twice.",
        "would_change_mind": "A sub-$8B price, or a signed plan to retire Quip and move its book to Notion within two quarters.",
        "evidence_audit": {
            "verified_pct": 20, "weak_pct": 35, "speculation_pct": 30, "unsupported_pct": 15,
            "integrity_note": "This offline sample runs on estimates, not live sources; treat every figure as directional until a live run checks them.",
            "audited_claims": [
                {"verdict": "SPECULATION", "seat": "Finance", "claim": "cross-sell synergy justifies a 30x ARR multiple", "reason": "No comparable deal cited; synergy figure is asserted."},
                {"verdict": "WEAK", "seat": "Market", "claim": "Notion ARR ~$400M", "reason": "Private company; figure is an estimate, not a filing."},
                {"verdict": "WEAK", "seat": "Technology", "claim": "4-6 engineer-quarters to integrate", "reason": "Plausible but unbenchmarked against a comparable integration."},
                {"verdict": "VERIFIED", "seat": "Competition", "claim": "Microsoft ships Loop inside M365", "reason": "Loop is a shipping M365 product."},
            ],
        },
        "board_vote": [
            {"member": "CEO", "vote": "NO-GO", "rationale": "The strategic story is seductive but I already own two seats on this surface. I would rather partner than pay a control premium for overlap."},
            {"member": "CFO", "vote": "NO-GO", "rationale": "A 30x multiple on estimated ARR with a double-counted synergy case is exactly the deal the audit tells me to decline. The same capital returns more via buyback."},
            {"member": "CTO", "vote": "NO-GO", "rationale": "Retiring Quip while merging three permission models is an optimistic 12 months. I would not commit the roadmap to it."},
            {"member": "General Counsel", "vote": "CONDITIONAL GO", "rationale": "No antitrust barrier at this share, so I would not block it. My concern is retention paper for founders, not regulators."},
        ],
        "conditions": [
            "Renegotiate below $8B or walk",
            "Signed Quip-retirement and customer-migration plan before close",
            "Founder + top-20 IC retention locked for 24 months",
        ],
    },

    # -----------------------------------------------------------------------
    "adobe_figma": {
        "id": "adobe_figma",
        "question": "Should Adobe acquire Figma?",
        "decision_type": "acquisition",
        "stakes": (
            "A ~$20B move to absorb the category-defining collaborative design "
            "tool - into the teeth of two antitrust regulators."
        ),
        "success_criteria": [
            "The deal clears EU and UK review without a remedy that guts the rationale.",
            "Figma keeps its independent brand and growth rather than being folded into Creative Cloud.",
            "XD's retirement converts to Figma seats instead of leaking to competitors.",
        ],
        "verdict": {
            "decision": "MORE INFORMATION REQUIRED",
            "confidence": 54,
            "strategic_fit": 8,
            "financial_risk": "MEDIUM",
            "regulatory_risk": "HIGH",
            "execution_risk": "MEDIUM",
            "chair_summary": (
                "More information required: the strategic fit is the best on the "
                "board, but the entire decision hinges on one binary the room "
                "cannot resolve - do the EU and UK clear it. Until outside "
                "antitrust counsel scores the remedy risk, a GO is a coin flip "
                "dressed as a strategy. A credible path to unconditional clearance "
                "flips this to GO."
            ),
        },
        "seats": [
            {
                "seat": "Market", "staffed": True,
                "headline": "Figma owns the collaborative-design standard Adobe missed.",
                "risk_score": 3, "conviction": 8,
                "opportunities": [
                    "Captures the multiplayer design category outright",
                    "Bridges Adobe into product-design teams it never reached",
                ],
                "risks": ["Buying the disruptor to stop being disrupted invites scrutiny"],
                "claims": [
                    {"claim": "Figma ARR at announcement", "figure": "~$400M ARR", "source": EST},
                    {"claim": "Figma share of collaborative UI design", "figure": "dominant among product teams", "source": EST},
                ],
            },
            {
                "seat": "Finance", "staffed": True,
                "headline": "~50x ARR is steep, but defensively rational if it clears.",
                "risk_score": 6, "conviction": 6,
                "opportunities": ["Removes the fastest threat to Creative Cloud pricing power"],
                "risks": [
                    "~50x ARR entry multiple",
                    "$1B reverse break-up fee if it is blocked",
                ],
                "claims": [
                    {"claim": "Headline price", "figure": "~$20B (half cash, half stock)", "source": EST},
                    {"claim": "Reverse termination fee", "figure": "~$1B", "source": EST},
                ],
            },
            {
                "seat": "Technology", "staffed": True,
                "headline": "Browser-native Figma and desktop Creative Cloud barely share a stack.",
                "risk_score": 4, "conviction": 6,
                "opportunities": ["Figma's web engine modernises Adobe's delivery"],
                "risks": ["Little real technical synergy; value is the asset, not the merge"],
                "claims": [
                    {"claim": "Architectural overlap", "figure": "low", "source": EST},
                ],
            },
            {
                "seat": "Competition", "staffed": True,
                "headline": "Removing Adobe's closest emerging rival is exactly what regulators inspect.",
                "risk_score": 7, "conviction": 7,
                "opportunities": ["Neutralises the most credible Creative Cloud challenger"],
                "risks": [
                    "Horizontal overlap with Adobe XD is the antitrust theory",
                    "Sketch, Canva and Penpot fill any vacuum a remedy creates",
                ],
                "claims": [
                    {"claim": "Adobe XD market position vs Figma", "figure": "trailing challenger", "source": EST},
                ],
            },
            {
                "seat": "Legal", "staffed": True,
                "headline": "Two regulators, a live horizontal theory - this is where the deal lives or dies.",
                "risk_score": 9, "conviction": 8,
                "opportunities": ["A clean clearance removes the overhang permanently"],
                "risks": [
                    "EU Phase II and UK CMA both plausible",
                    "'Buying to neutralise a nascent competitor' is the current enforcement priority",
                ],
                "claims": [
                    {"claim": "Probability of an in-depth EU/UK review", "figure": "high", "source": EST},
                ],
            },
        ],
        "attacks": [
            {"severity": 10, "deal_breaker": True, "target_seat": "Legal",
             "claim_attacked": "the deal closes as signed",
             "why_it_breaks": "Both the EU and UK are primed to treat an incumbent buying its fastest-growing rival as a horizontal problem; the base rate for unconditional clearance here is low."},
            {"severity": 7, "deal_breaker": False, "target_seat": "Finance",
             "claim_attacked": "50x ARR is defensible",
             "why_it_breaks": "It is only defensible if the deal clears; risk-adjusted for a plausible block, the expected multiple is far worse once you add the reverse break fee and two lost years."},
            {"severity": 6, "deal_breaker": False, "target_seat": "Market",
             "claim_attacked": "Figma keeps its brand and growth inside Adobe",
             "why_it_breaks": "Acquired category leaders routinely lose momentum and key staff during a multi-year regulatory limbo, before any integration even starts."},
            {"severity": 5, "deal_breaker": False, "target_seat": "Competition",
             "claim_attacked": "the deal removes the main challenger",
             "why_it_breaks": "Canva and open-source Penpot already occupy adjacent ground; the vacuum refills whether or not Figma is absorbed."},
        ],
        "kill_shot": "You are betting $20B and two years on a regulatory coin flip that the current enforcement climate has weighted against you.",
        "would_change_mind": "A written opinion from outside antitrust counsel putting unconditional EU + UK clearance above 60%.",
        "evidence_audit": {
            "verified_pct": 30, "weak_pct": 30, "speculation_pct": 25, "unsupported_pct": 15,
            "integrity_note": "The regulatory theory is well-grounded; the financial synergy claims are estimates. The decision rests almost entirely on the one claim the board cannot itself verify.",
            "audited_claims": [
                {"verdict": "VERIFIED", "seat": "Competition", "claim": "Adobe XD and Figma overlap in UI design", "reason": "Both are UI-design tools; overlap is factual."},
                {"verdict": "WEAK", "seat": "Finance", "claim": "~50x ARR entry multiple", "reason": "Depends on an estimated private ARR."},
                {"verdict": "SPECULATION", "seat": "Legal", "claim": "high probability of in-depth review", "reason": "Directionally sound but needs counsel to quantify."},
                {"verdict": "UNSUPPORTED", "seat": "Market", "claim": "Figma keeps 40%+ growth through close", "reason": "No basis provided for growth through a multi-year review."},
            ],
        },
        "board_vote": [
            {"member": "CEO", "vote": "GO", "rationale": "This is the best strategic fit we will ever see in this category. I want it if counsel can get it through."},
            {"member": "CFO", "vote": "MORE INFORMATION REQUIRED", "rationale": "I cannot price a deal whose expected value swings entirely on a regulatory binary. Get me the clearance probability first."},
            {"member": "CTO", "vote": "GO", "rationale": "Low integration risk - we are buying an asset, not merging a stack. My concerns are the smallest at this table."},
            {"member": "General Counsel", "vote": "MORE INFORMATION REQUIRED", "rationale": "I will not sign off on 'will be challenged' vs 'will be blocked' without outside counsel scoring the remedy risk. That gate comes before any vote."},
        ],
        "conditions": [
            "Outside antitrust opinion on EU + UK clearance before board approval",
            "Reverse break fee sized to cover two years of strategic delay",
            "Standalone-brand and independent-roadmap commitment for Figma",
        ],
    },

    # -----------------------------------------------------------------------
    "spotify_audiobooks": {
        "id": "spotify_audiobooks",
        "question": "Should Spotify launch a standalone audiobooks subscription?",
        "decision_type": "product launch",
        "stakes": (
            "A new subscription tier to turn Spotify's audiobook catalogue into a "
            "second recurring line, without cannibalising Premium."
        ),
        "success_criteria": [
            "The tier reaches 5M paying subscribers in 18 months at positive contribution margin.",
            "Fewer than 15% of subscribers are Premium users trading down.",
            "Per-title licensing stays below the price that erases the margin.",
        ],
        "verdict": {
            "decision": "GO",
            "confidence": 72,
            "strategic_fit": 8,
            "financial_risk": "MEDIUM",
            "regulatory_risk": "LOW",
            "execution_risk": "MEDIUM",
            "chair_summary": (
                "Go, conditionally: Spotify already has the catalogue, the "
                "distribution and the payment rails, so the marginal cost of the "
                "tier is low and the downside is contained. The one real risk is "
                "Premium cannibalisation, which is measurable and reversible. Ship "
                "it as a controlled launch with a hard cannibalisation tripwire."
            ),
        },
        "seats": [
            {
                "seat": "Market", "staffed": True,
                "headline": "Audiobooks are the fastest-growing audio segment and Spotify already has the users.",
                "risk_score": 3, "conviction": 8,
                "opportunities": [
                    "600M+ existing users to convert at near-zero CAC",
                    "Audiobooks grow double digits while music streaming matures",
                ],
                "risks": ["Amazon/Audible owns the incumbent habit"],
                "claims": [
                    {"claim": "Spotify monthly active users", "figure": "~600M MAU", "source": EST},
                    {"claim": "Audiobook market growth", "figure": "~25% CAGR", "source": EST},
                ],
            },
            {
                "seat": "Finance", "staffed": True,
                "headline": "Low incremental cost on an owned catalogue, but per-title licensing is the swing factor.",
                "risk_score": 5, "conviction": 6,
                "opportunities": ["Second recurring line diversifies away from music-label economics"],
                "risks": [
                    "Consumption-based publisher licensing can invert unit economics",
                    "Heavy listeners are unprofitable under all-you-can-read pricing",
                ],
                "claims": [
                    {"claim": "Incremental infra cost per new tier subscriber", "figure": "low", "source": EST},
                ],
            },
            {
                "seat": "Technology", "staffed": True,
                "headline": "The app already ships audiobooks; a tier is packaging, not a rebuild.",
                "risk_score": 2, "conviction": 8,
                "opportunities": ["Reuses existing playback, entitlements and billing"],
                "risks": ["Entitlement/paywall logic across tiers needs care"],
                "claims": [
                    {"claim": "Net-new engineering to launch the tier", "figure": "1-2 engineer-quarters", "source": EST},
                ],
            },
            {
                "seat": "Competition", "staffed": True,
                "headline": "Audible is entrenched but priced high; a bundled-feel tier undercuts it.",
                "risk_score": 4, "conviction": 6,
                "opportunities": ["Price and UX advantage over a single-purpose Audible app"],
                "risks": ["Amazon can retaliate by bundling Audible into Prime"],
                "claims": [
                    {"claim": "Audible standalone price point", "figure": "premium vs proposed tier", "source": EST},
                ],
            },
            {
                "seat": "Legal", "staffed": False,
                "bench_reason": "Standard content-licensing, no novel regulatory exposure; benched.",
                "headline": "", "risk_score": 2, "conviction": 5,
                "opportunities": [], "risks": [],
            },
        ],
        "attacks": [
            {"severity": 7, "deal_breaker": False, "target_seat": "Finance",
             "claim_attacked": "low incremental cost makes the tier profitable",
             "why_it_breaks": "Under consumption-based publisher licensing, the heaviest 10% of listeners can be structurally unprofitable, exactly the users an all-you-can-listen tier attracts."},
            {"severity": 6, "deal_breaker": False, "target_seat": "Market",
             "claim_attacked": "600M users convert at near-zero CAC",
             "why_it_breaks": "Most of those conversions are Premium users trading laterally, which is cannibalisation booked as growth."},
            {"severity": 4, "deal_breaker": False, "target_seat": "Competition",
             "claim_attacked": "a price advantage beats Audible",
             "why_it_breaks": "Amazon can neutralise price overnight by folding Audible into Prime, turning a price war into an attrition Spotify funds alone."},
            {"severity": 3, "deal_breaker": False, "target_seat": "Technology",
             "claim_attacked": "it is only packaging work",
             "why_it_breaks": "Cross-tier entitlement bugs are the classic launch-day incident; low effort is not low risk."},
        ],
        "kill_shot": "The tier only makes money if your best customers don't binge and your Premium base doesn't trade down - and this tier is designed to make both happen.",
        "would_change_mind": "A cohort test showing under 15% Premium trade-down and positive margin on the top listening decile.",
        "evidence_audit": {
            "verified_pct": 35, "weak_pct": 30, "speculation_pct": 20, "unsupported_pct": 15,
            "integrity_note": "The strategic and technical claims are solid; the profitability case rests on licensing terms that a live run should pull from filings.",
            "audited_claims": [
                {"verdict": "VERIFIED", "seat": "Market", "claim": "Spotify has ~600M MAU", "reason": "Consistent with reported user scale."},
                {"verdict": "VERIFIED", "seat": "Technology", "claim": "the app already offers audiobooks", "reason": "Audiobooks are a shipped Spotify feature."},
                {"verdict": "WEAK", "seat": "Finance", "claim": "incremental cost is low", "reason": "True for infra, silent on per-title licensing which dominates."},
                {"verdict": "SPECULATION", "seat": "Market", "claim": "~25% audiobook CAGR", "reason": "Directional industry estimate, unsourced here."},
            ],
        },
        "board_vote": [
            {"member": "CEO", "vote": "GO", "rationale": "We own the catalogue, the users and the rails. This is the cheapest second revenue line we can start."},
            {"member": "CFO", "vote": "CONDITIONAL GO", "rationale": "I am in, provided we cap exposure to consumption-based licensing and set a hard cannibalisation tripwire before scaling spend."},
            {"member": "CTO", "vote": "GO", "rationale": "One-to-two quarters of packaging on shipped infrastructure. This is the lowest execution risk we have looked at."},
            {"member": "General Counsel", "vote": "GO", "rationale": "Ordinary content licensing, no novel regulatory exposure. No objection."},
        ],
        "conditions": [
            "Controlled launch with a hard Premium-cannibalisation tripwire",
            "Cap or renegotiate consumption-based publisher licensing before scaling marketing",
            "Margin gate on the top listening decile before national rollout",
        ],
    },
}


# question keyword -> sample id, checked in order
_MATCHERS: list[tuple[tuple[str, ...], str]] = [
    (("salesforce", "notion"), "salesforce_notion"),
    (("adobe", "figma"), "adobe_figma"),
    (("spotify",), "spotify_audiobooks"),
]


def list_samples() -> list[dict]:
    return list(SAMPLES.values())


def match(question: str) -> str | None:
    """Map a free-text question to a curated sample id, or None."""
    q = (question or "").lower()
    for needles, sample_id in _MATCHERS:
        if all(n in q for n in needles):
            return sample_id
    return None
