"""Curated demo dataset - lets the whole application run instantly, offline.

The live sources are slow (cold-start OFAC download, GDELT rate limits), so this
provides three fictional subjects with pre-authored adverse media, litigation,
ownership and insider-transaction fixtures. Adverse-media categories and bias
scores are computed by the real taxonomy and bias analyzer, so the demo
exercises the same code paths a live investigation would.

Every entity here is invented. Real companies are never given fabricated
allegations.
"""

from __future__ import annotations

from app.risk import bias
from app.risk.engine import evaluate, recommendation
from app.risk.taxonomy import categories_for

# --------------------------------------------------------------------------
# Adverse-media articles. Bias varies deliberately: neutral wire copy, mixed
# reporting, and openly editorial / tabloid pieces, so the objectivity filter
# has something to separate. (subject, source, date, title, body)
# --------------------------------------------------------------------------
ARTICLES: list[dict] = [
    # ---- Northwind Trading Co. -------------------------------------------
    {"subject": "northwind", "source": "Reuters", "date": "2025-11-12",
     "title": "Northwind Trading Co. fined $12m over anti-money-laundering lapses",
     "body": "Regulators fined Northwind Trading Co. $12 million after finding weaknesses in its anti-money laundering controls. The company said it has since strengthened its compliance program. No individuals were charged."},
    {"subject": "northwind", "source": "The Daily Ledger", "date": "2025-11-13",
     "title": "Shocking: how crooked Northwind allegedly laundered millions under everyone's nose",
     "body": "In a truly shocking scandal, insiders say the crooked bosses at Northwind reportedly laundered staggering sums while regulators slept. Everyone knows this is just the tip of the iceberg. Critics say the firm is rotten to the core."},
    {"subject": "northwind", "source": "Bloomberg", "date": "2025-10-28",
     "title": "FINRA opens enforcement review into Northwind trade reporting",
     "body": "FINRA has opened an enforcement action review into Northwind Trading Co. over alleged trade-reporting failures. The regulator's investigation is at an early stage. Northwind said it is cooperating fully."},
    {"subject": "northwind", "source": "Financial Times", "date": "2025-09-30",
     "title": "Northwind faces shareholder class action over disclosures",
     "body": "A shareholder class action was filed against Northwind Trading Co. alleging inadequate disclosure of compliance risks. The litigation is pending in a federal court. The company declined to comment on ongoing litigation."},
    {"subject": "northwind", "source": "Associated Press", "date": "2025-08-15",
     "title": "Northwind unit removed from supplier list pending sanctions review",
     "body": "A European buyer removed a Northwind subsidiary from its approved supplier list pending a sanctions review. The review concerns potential export control exposure. Northwind said none of its units are subject to sanctions."},
    {"subject": "northwind", "source": "Regional Wire", "date": "2025-07-20",
     "title": "Prosecutors probe smuggling claims tied to Northwind cargo",
     "body": "Prosecutors are examining whether a shipment linked to Northwind Trading Co. was used for smuggling. No charges have been filed. Northwind said it was unaware of any misuse of its cargo."},
    {"subject": "northwind", "source": "The Street Whisper", "date": "2025-07-02",
     "title": "Make no mistake: Northwind's fraud is the worst I've ever seen",
     "body": "Make no mistake, the fraud at Northwind is obviously the worst this industry has ever seen. Any reasonable person can see the numbers are fabricated. The truth is, nobody at the top is clean."},
    {"subject": "northwind", "source": "Compliance Weekly", "date": "2025-06-18",
     "title": "Northwind agrees consent order with state regulator",
     "body": "Northwind Trading Co. agreed to a consent order with a state regulator to resolve a disclosure violation. The order includes a monetary penalty and independent monitoring. The company neither admitted nor denied the findings."},
    {"subject": "northwind", "source": "City Gazette", "date": "2025-05-22",
     "title": "Northwind executive resigns amid mounting controversy",
     "body": "A senior Northwind executive resigns amid mounting controversy over the firm's risk culture. Some say the departure was overdue. The company thanked the executive for years of service."},
    {"subject": "northwind", "source": "Reuters", "date": "2025-04-10",
     "title": "Northwind settles bribery allegations for $8m",
     "body": "Northwind Trading Co. agreed to pay $8 million to settle allegations that a former agent paid a bribe to win contracts. The settlement resolves a multi-year investigation. Northwind said the conduct violated its policies."},
    {"subject": "northwind", "source": "Trade Compliance Digest", "date": "2025-03-14",
     "title": "Northwind flagged in export-control audit",
     "body": "An export control audit flagged several Northwind transactions for further review over potential restricted party exposure. The audit did not conclude that violations occurred. Northwind said it screens all counterparties."},
    {"subject": "northwind", "source": "The Daily Ledger", "date": "2025-02-28",
     "title": "Explosive claims link notorious Northwind to arms trafficking ring",
     "body": "In an explosive report, sources claim the notorious traders at Northwind were tied to an arms trafficking ring. Word on the street is that this is only the beginning. The allegations are damning."},
    {"subject": "northwind", "source": "Bloomberg", "date": "2025-01-19",
     "title": "Northwind disclosed as subject of SEC charges over reporting",
     "body": "Northwind Trading Co. disclosed that it is the subject of SEC charges relating to inaccurate regulatory reporting. The company is contesting the charges. A hearing is scheduled for next quarter."},
    {"subject": "northwind", "source": "Investor Post", "date": "2024-12-05",
     "title": "Auditors flag possible misappropriation at Northwind subsidiary",
     "body": "External auditors flagged possible misappropriation of funds at a Northwind subsidiary. The board commissioned an independent review. Preliminary findings are expected next quarter."},
    {"subject": "northwind", "source": "National Tribune", "date": "2024-11-11",
     "title": "Disgraceful: Northwind's sordid cover-up exposed",
     "body": "It is utterly disgraceful. The sordid cover-up at Northwind has finally been exposed, and critics say heads must roll. Everyone knows the board looked the other way."},
    {"subject": "northwind", "source": "Associated Press", "date": "2024-10-02",
     "title": "Northwind counterparty added to watchlist by lender",
     "body": "A lender added a Northwind counterparty to its internal watchlist after a routine screening. Northwind said the counterparty relationship has since ended. No regulator has designated the entity."},
    {"subject": "northwind", "source": "Regional Wire", "date": "2024-09-08",
     "title": "Northwind named in indictment over narcotics-linked shipment",
     "body": "A federal indictment named a logistics contractor used by Northwind in connection with a narcotics shipment. Northwind is not itself charged. The company said it has suspended the contractor."},
    {"subject": "northwind", "source": "Reuters", "date": "2024-08-14",
     "title": "Northwind discloses internal probe into insider trading",
     "body": "Northwind Trading Co. disclosed an internal probe into possible insider trading by a former employee. The matter has been referred to regulators. The company said it acted promptly on a whistleblower report."},
    {"subject": "northwind", "source": "Compliance Weekly", "date": "2024-07-01",
     "title": "Northwind hit with penalty over compliance failure",
     "body": "Northwind Trading Co. was hit with a penalty over a compliance failure in its trade surveillance systems. The firm agreed to remediation milestones. An independent monitor will report quarterly."},
    {"subject": "northwind", "source": "City Gazette", "date": "2024-06-19",
     "title": "Northwind boycott gathers pace among retail partners",
     "body": "A boycott of Northwind is gathering pace among some retail partners citing reputational concerns. Many believe the pressure will force change. The company said it remains in dialogue with partners."},

    # ---- Meridian Capital Partners ---------------------------------------
    {"subject": "meridian", "source": "Bloomberg", "date": "2025-10-10",
     "title": "FINRA censures Meridian Capital over supervision lapses",
     "body": "FINRA censured Meridian Capital Partners over supervision lapses and imposed a fine. The firm consented to the findings without admitting wrongdoing. Meridian said it upgraded its supervisory systems."},
    {"subject": "meridian", "source": "Financial Times", "date": "2025-09-05",
     "title": "Meridian founder charged with securities fraud",
     "body": "The founder of Meridian Capital Partners was charged with securities fraud in connection with client account statements. The founder denies the charges. Meridian said the individual is on leave."},
    {"subject": "meridian", "source": "The Street Whisper", "date": "2025-08-01",
     "title": "Obviously a scam: Meridian's genius founder is anything but",
     "body": "Obviously this was a fraud from day one. The so-called genius behind Meridian is, plain and simple, a crook. Make no mistake, investors were utterly fleeced."},
    {"subject": "meridian", "source": "Trade Compliance Digest", "date": "2025-06-20",
     "title": "Meridian fund exposure to sanctioned issuer under review",
     "body": "Meridian Capital Partners is reviewing a fund's exposure to a recently sanctioned issuer. The firm said the position is being unwound. Regulators have not alleged any violation."},
    {"subject": "meridian", "source": "City Gazette", "date": "2025-05-02",
     "title": "Investors file class action against Meridian over fees",
     "body": "Investors filed a class action against Meridian Capital Partners over allegedly undisclosed fees. The litigation is at an early stage. Meridian said the fees were fully disclosed."},
    {"subject": "meridian", "source": "Compliance Weekly", "date": "2025-03-18",
     "title": "Meridian adviser barred then reinstated after appeal",
     "body": "An adviser previously barred in connection with Meridian Capital Partners was reinstated after a successful appeal. The regulator did not comment. Meridian welcomed the decision."},
    {"subject": "meridian", "source": "National Tribune", "date": "2025-02-14",
     "title": "Damning new claims: Meridian's brazen embezzlement laid bare",
     "body": "Damning new claims allege brazen embezzlement at Meridian. Sources say the scale is staggering and that nobody in management can be trusted. It is, frankly, appalling."},
    {"subject": "meridian", "source": "Reuters", "date": "2025-01-08",
     "title": "Meridian enters consent order over disclosure violation",
     "body": "Meridian Capital Partners entered a consent order to resolve a disclosure violation. The order carries a monetary penalty. The firm neither admitted nor denied the findings."},

    # ---- Halcyon Logistics Ltd -------------------------------------------
    {"subject": "halcyon", "source": "Associated Press", "date": "2025-09-22",
     "title": "Halcyon vessel detained in human-trafficking investigation",
     "body": "A vessel operated by Halcyon Logistics was detained as part of a human trafficking investigation. No charges have been filed against the company. Halcyon said it is cooperating with authorities."},
    {"subject": "halcyon", "source": "Trade Compliance Digest", "date": "2025-08-11",
     "title": "Halcyon route flagged for embargo exposure",
     "body": "A shipping route used by Halcyon Logistics was flagged for potential embargo exposure. The firm said it rerouted affected shipments. No enforcement action has been taken."},
    {"subject": "halcyon", "source": "National Tribune", "date": "2025-07-04",
     "title": "Sinister cargo: Halcyon's alleged smuggling empire exposed",
     "body": "In a sinister twist, sources claim Halcyon ran a smuggling empire hiding in plain sight. Everyone knows the docks talk, and the rumors are damning. This is reckless corporate greed at its worst."},
    {"subject": "halcyon", "source": "Reuters", "date": "2025-06-01",
     "title": "Halcyon settles customs-fraud allegations",
     "body": "Halcyon Logistics agreed to settle customs fraud allegations for an undisclosed sum. The settlement resolves a civil inquiry. Halcyon said it has overhauled its customs procedures."},
    {"subject": "halcyon", "source": "Bloomberg", "date": "2025-04-27",
     "title": "Regulator fines Halcyon over safety-reporting failures",
     "body": "A transport regulator fined Halcyon Logistics over safety-reporting failures. The firm agreed to a remediation plan. An independent auditor will verify compliance."},
    {"subject": "halcyon", "source": "City Gazette", "date": "2025-03-09",
     "title": "Halcyon faces negligence suit after warehouse fire",
     "body": "Halcyon Logistics faces a negligence lawsuit after a warehouse fire damaged client goods. Some say safety was neglected for years. The company said the cause is still under investigation."},
    {"subject": "halcyon", "source": "Associated Press", "date": "2025-01-30",
     "title": "Halcyon counterparty designated under new sanctions program",
     "body": "A counterparty of Halcyon Logistics was designated under a new sanctions program. Halcyon said it terminated the relationship immediately. The firm reported the exposure to its bank."},
]


# --------------------------------------------------------------------------
# Subject fixtures - identity, sanctions, litigation, ownership, transactions.
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Cross-entity connection graph. Persons sit on multiple boards, holding
# companies own several subsidiaries, and shared officers link the three
# subjects to each other - the multi-hop network a Neo4j-style investigation
# would surface. Every edge carries a description so a connection can be
# explained by the AI insight agent.
# --------------------------------------------------------------------------
GRAPH_NODES: dict[str, dict] = {
    "Northwind Trading Co.": {"type": "entity", "detail": "Commodities trader (US)"},
    "Meridian Capital Partners": {"type": "entity", "detail": "Asset manager (US)"},
    "Halcyon Logistics Ltd": {"type": "entity", "detail": "Logistics operator (UK)"},

    "Northwind Holdings B.V.": {"type": "holding", "detail": "Ultimate parent (Netherlands)"},
    "Northwind Trading Cayman Ltd": {"type": "holding", "detail": "Direct parent (Cayman Islands)"},
    "Halcyon Group Holdings Ltd": {"type": "holding", "detail": "Ultimate parent (UK)"},
    "Coastal Nominees Ltd": {"type": "holding", "detail": "Direct parent (Jersey)"},

    "Grace Halloran": {"type": "person", "detail": "Chief Executive Officer, Northwind"},
    "Peter Vance": {"type": "person", "detail": "Chief Financial Officer, Northwind"},
    "Marcus Reed": {"type": "person", "detail": "VP Trading, Northwind"},
    "Julian Frost": {"type": "person", "detail": "Founder, Meridian (on leave)"},
    "Anita Bose": {"type": "person", "detail": "Chief Compliance Officer, Meridian"},

    "Aurora Commodities Ltd": {"type": "company", "detail": "External firm (UK)"},
    "Baltic Shipping AS": {"type": "company", "detail": "External firm (Norway)"},
    "Sterling Advisory Group": {"type": "company", "detail": "External firm (US)"},
    "Vance Family Office": {"type": "trust", "detail": "Private investment vehicle"},
    "Frost Family Trust": {"type": "trust", "detail": "Discretionary trust"},
}

GRAPH_EDGES: list[dict] = [
    # Northwind core
    {"source": "Grace Halloran", "target": "Northwind Trading Co.", "rel": "Chief Executive Officer",
     "confidence": 0.86, "description": "Grace Halloran is CEO of Northwind Trading Co. and its most senior insider seller in the last year."},
    {"source": "Peter Vance", "target": "Northwind Trading Co.", "rel": "Chief Financial Officer",
     "confidence": 0.83, "description": "Peter Vance is CFO of Northwind Trading Co.; he signed the filings tied to the AML enforcement review."},
    {"source": "Marcus Reed", "target": "Northwind Trading Co.", "rel": "VP Trading",
     "confidence": 0.7, "description": "Marcus Reed runs trading at Northwind and holds options exercised earlier this year."},
    {"source": "Northwind Holdings B.V.", "target": "Northwind Trading Co.", "rel": "Ultimate parent",
     "confidence": 0.88, "description": "Northwind Holdings B.V., a Dutch entity, is the ultimate parent of Northwind Trading Co."},
    {"source": "Northwind Trading Cayman Ltd", "target": "Northwind Trading Co.", "rel": "Direct parent",
     "confidence": 0.84, "description": "Northwind Trading Cayman Ltd is the direct parent, adding an offshore layer to the ownership chain."},
    {"source": "Northwind Trading Cayman Ltd", "target": "Northwind Holdings B.V.", "rel": "Subsidiary of",
     "confidence": 0.88, "description": "The Cayman entity is itself a subsidiary of Northwind Holdings B.V., forming a two-tier offshore structure."},

    # Cross-entity links via shared people / parents
    {"source": "Grace Halloran", "target": "Aurora Commodities Ltd", "rel": "Non-executive director",
     "confidence": 0.72, "description": "Grace Halloran also sits on the board of Aurora Commodities Ltd, an unrelated commodities firm."},
    {"source": "Peter Vance", "target": "Meridian Capital Partners", "rel": "Advisory board member",
     "confidence": 0.66, "description": "Peter Vance advises Meridian Capital Partners, creating a direct link between two investigated entities."},
    {"source": "Peter Vance", "target": "Vance Family Office", "rel": "Principal",
     "confidence": 0.8, "description": "Peter Vance controls the Vance Family Office, a private vehicle holding personal investments."},
    {"source": "Northwind Holdings B.V.", "target": "Baltic Shipping AS", "rel": "Owns 60%",
     "confidence": 0.8, "description": "Northwind's Dutch parent owns a controlling 60% stake in Baltic Shipping AS."},
    {"source": "Marcus Reed", "target": "Halcyon Logistics Ltd", "rel": "Board observer",
     "confidence": 0.6, "description": "Marcus Reed is a board observer at Halcyon Logistics Ltd, linking Northwind to a third investigated entity."},

    # Meridian
    {"source": "Julian Frost", "target": "Meridian Capital Partners", "rel": "Founder",
     "confidence": 0.8, "description": "Julian Frost founded Meridian Capital Partners and faces securities-fraud charges."},
    {"source": "Anita Bose", "target": "Meridian Capital Partners", "rel": "Chief Compliance Officer",
     "confidence": 0.82, "description": "Anita Bose is Meridian's Chief Compliance Officer."},
    {"source": "Julian Frost", "target": "Frost Family Trust", "rel": "Settlor",
     "confidence": 0.78, "description": "Julian Frost is the settlor of the Frost Family Trust, which holds part of his Meridian stake."},
    {"source": "Julian Frost", "target": "Sterling Advisory Group", "rel": "Non-executive director",
     "confidence": 0.65, "description": "Julian Frost also serves as a director of Sterling Advisory Group."},

    # Halcyon
    {"source": "Halcyon Group Holdings Ltd", "target": "Halcyon Logistics Ltd", "rel": "Ultimate parent",
     "confidence": 0.86, "description": "Halcyon Group Holdings Ltd is the ultimate parent of Halcyon Logistics Ltd."},
    {"source": "Coastal Nominees Ltd", "target": "Halcyon Logistics Ltd", "rel": "Direct parent",
     "confidence": 0.78, "description": "Coastal Nominees Ltd, a Jersey entity, is the direct parent of Halcyon Logistics Ltd."},
    {"source": "Coastal Nominees Ltd", "target": "Halcyon Group Holdings Ltd", "rel": "Subsidiary of",
     "confidence": 0.8, "description": "Coastal Nominees Ltd is a subsidiary of Halcyon Group Holdings Ltd."},
]


SUBJECTS: dict[str, dict] = {
    "northwind": {
        "name": "Northwind Trading Co.",
        "entity_type": "organization",
        "country": "United States",
        "website": "northwindtrading.example",
        "aliases": ["Northwind Commodities", "Northwind Trading LLC"],
        "registration": "CIK:0009900001",
        "lei": "5493DEMO0NORTHWIND01",
        "cik": "0009900001",
        "identity_confidence": 0.91,
        "status": "verified",
        "tagline": "Commodities trader - heaviest adverse-media load",
        "sanctions_list_size": 39564,
        "litigation": [
            {"case": "In re Northwind Securities Litigation", "court": "S.D.N.Y.",
             "date": "2025-09-30", "confidence": 0.92,
             "url": "https://www.courtlistener.com/", "nature_of_suit": "Securities"},
            {"case": "Doe v. Northwind Trading Co.", "court": "D. Del.",
             "date": "2025-04-10", "confidence": 0.86, "url": None,
             "nature_of_suit": "Contract"},
            {"case": "SEC v. Northwind Trading Co.", "court": "S.D.N.Y.",
             "date": "2025-01-19", "confidence": 0.9, "url": None,
             "nature_of_suit": "Securities"},
        ],
        "ownership": [
            {"name": "Grace Halloran", "role": "Chief Executive Officer",
             "relationship_type": "officer_or_director", "confidence": 0.86},
            {"name": "Peter Vance", "role": "Chief Financial Officer",
             "relationship_type": "officer_or_director", "confidence": 0.83},
            {"name": "Northwind Holdings B.V.", "role": "Ultimate Parent",
             "relationship_type": "ultimate_parent", "country": "Netherlands",
             "confidence": 0.88},
            {"name": "Northwind Trading Cayman Ltd", "role": "Direct Parent",
             "relationship_type": "direct_parent", "country": "Cayman Islands",
             "confidence": 0.84},
        ],
        "transactions": [
            {"insider": "Grace Halloran", "date": "2025-08-15", "code": "S",
             "code_label": "Open-market sale", "direction": "disposed",
             "shares": 40000, "price_per_share": 21.5},
            {"insider": "Grace Halloran", "date": "2025-06-11", "code": "S",
             "code_label": "Open-market sale", "direction": "disposed",
             "shares": 25000, "price_per_share": 24.1},
            {"insider": "Peter Vance", "date": "2025-05-30", "code": "S",
             "code_label": "Open-market sale", "direction": "disposed",
             "shares": 18000, "price_per_share": 23.4},
            {"insider": "Peter Vance", "date": "2025-03-02", "code": "P",
             "code_label": "Open-market purchase", "direction": "acquired",
             "shares": 5000, "price_per_share": 19.8},
            {"insider": "Marcus Reed", "date": "2025-02-18", "code": "M",
             "code_label": "Option exercise", "direction": "acquired",
             "shares": 12000, "price_per_share": 12.0},
        ],
        "alternatives": [
            {"name": "Northwind Energy Partners LP", "source": "SEC", "confidence": 0.58,
             "confidence_breakdown": {"name": 0.71, "embedding": 0.55, "address": 0.0}},
            {"name": "Northwind Realty Trust", "source": "SEC", "confidence": 0.49,
             "confidence_breakdown": {"name": 0.62, "embedding": 0.44, "address": 0.0}},
        ],
    },
    "meridian": {
        "name": "Meridian Capital Partners",
        "entity_type": "organization",
        "country": "United States",
        "website": "meridiancapital.example",
        "aliases": ["Meridian Capital", "Meridian Partners LLC"],
        "registration": "CIK:0009900002",
        "lei": "5493DEMO0MERIDIAN02",
        "cik": "0009900002",
        "identity_confidence": 0.84,
        "status": "verified",
        "tagline": "Asset manager - founder securities-fraud charge",
        "sanctions_list_size": 39564,
        "litigation": [
            {"case": "US v. [Meridian founder]", "court": "S.D.N.Y.",
             "date": "2025-09-05", "confidence": 0.9, "url": None,
             "nature_of_suit": "Securities Fraud"},
            {"case": "Investors v. Meridian Capital Partners", "court": "D. Mass.",
             "date": "2025-05-02", "confidence": 0.84, "url": None,
             "nature_of_suit": "Securities"},
        ],
        "ownership": [
            {"name": "Julian Frost", "role": "Founder (on leave)",
             "relationship_type": "officer_or_director", "confidence": 0.8},
            {"name": "Anita Bose", "role": "Chief Compliance Officer",
             "relationship_type": "officer_or_director", "confidence": 0.82},
        ],
        "transactions": [
            {"insider": "Julian Frost", "date": "2025-07-28", "code": "S",
             "code_label": "Open-market sale", "direction": "disposed",
             "shares": 60000, "price_per_share": 44.0},
            {"insider": "Anita Bose", "date": "2025-04-15", "code": "P",
             "code_label": "Open-market purchase", "direction": "acquired",
             "shares": 3000, "price_per_share": 38.5},
        ],
        "alternatives": [
            {"name": "Meridian Wealth Advisors", "source": "SEC", "confidence": 0.6,
             "confidence_breakdown": {"name": 0.73, "embedding": 0.57, "address": 0.0}},
        ],
    },
    "halcyon": {
        "name": "Halcyon Logistics Ltd",
        "entity_type": "organization",
        "country": "United Kingdom",
        "website": "halcyonlogistics.example",
        "aliases": ["Halcyon Shipping", "Halcyon Logistics International"],
        "registration": "LEI:5493DEMO0HALCYON03",
        "lei": "5493DEMO0HALCYON03",
        "cik": None,
        "identity_confidence": 0.79,
        "status": "probable",
        "tagline": "UK logistics - serious-crime and sanctions exposure",
        "sanctions_list_size": 39564,
        "litigation": [
            {"case": "Acme Freight v. Halcyon Logistics Ltd", "court": "QBD",
             "date": "2025-03-09", "confidence": 0.82, "url": None,
             "nature_of_suit": "Negligence"},
        ],
        "ownership": [
            {"name": "Halcyon Group Holdings Ltd", "role": "Ultimate Parent",
             "relationship_type": "ultimate_parent", "country": "United Kingdom",
             "confidence": 0.86},
            {"name": "Coastal Nominees Ltd", "role": "Direct Parent",
             "relationship_type": "direct_parent", "country": "Jersey",
             "confidence": 0.78},
        ],
        # Non-US entity: no Section 16 filing obligation, so no Form 4 data.
        "transactions": [],
        "alternatives": [
            {"name": "Halcyon Freight Services", "source": "GLEIF", "confidence": 0.55,
             "confidence_breakdown": {"name": 0.68, "embedding": 0.5, "address": 1.0}},
        ],
    },
}
