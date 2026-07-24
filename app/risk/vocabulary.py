"""Risk-term vocabulary and category routing.

A large controlled vocabulary of adverse-media risk terms, each routed to one of
the five top-level categories. Used by the cosine term-matcher and the word
cloud. Routing is rule-based and ordered (most severe category wins) so a term
like "terrorist financing" lands in Terrorism & Serious Crime, not Financial
Crime, even though it contains "financing".
"""

from __future__ import annotations

# Ordered (category_key, trigger substrings). First match wins, so the most
# severe categories are checked first.
_ROUTES: list[tuple[str, tuple[str, ...]]] = [
    ("terrorism_serious_crime", (
        "terror", "extremis", "radical", "militant", "insurgen", "separatist",
        "jihad", "war crime", "crimes against humanity", "genocide", "ethnic cleansing",
        "traffick", "smuggl", "cartel", "narcotic", "drug", "organized crime",
        "organised crime", "crime syndicate", "criminal organization", "criminal network",
        "mafia", "racketeer", "weapon", "arms", "nuclear", "chemical weapon",
        "biological weapon", "wmd", "mass destruction", "missile", "murder",
        "kidnap", "assassinat", "hostage", "bombing", "explosion", "terror attack",
        "violent", "slavery", "forced labor", "forced labour", "forced recruitment",
        "child labor", "child exploitation", "child traffick", "sexual exploitation",
        "human right", "torture", "hate crime", "hate group", "militia", "armed conflict",
        "civil war", "coup", "riot", "war crimes", "wildlife traffick", "conflict mineral",
    )),
    ("sanctions", (
        "sanction", "ofac", "embargo", "export control", "export violation",
        "watchlist", "blacklist", "blocked entity", "restricted entity", "restricted party",
        "denied party", "designated", "asset freeze", "asset freezing", "frozen asset",
        "politically exposed", "pep", "arms embargo", "trade restriction",
    )),
    ("financial_crime", (
        "launder", "money mule", "structuring", "smurfing", "fraud", "embezzl",
        "bribe", "bribery", "corruption", "kickback", "graft", "extortion", "blackmail",
        "ponzi", "pyramid scheme", "insider trading", "insider dealing", "market manipulation",
        "market abuse", "price manipulation", "stock manipulation", "front running",
        "tax evasion", "tax avoidance", "shell company", "shell corporation",
        "beneficial ownership", "hidden asset", "asset conceal", "wealth conceal",
        "unexplained wealth", "dirty money", "illicit fund", "illegal proceed",
        "criminal proceed", "counterfeit currency", "counterfeit money", "fake currency",
        "crypto scam", "crypto laundering", "cryptocurrency fraud", "digital asset fraud",
        "blockchain fraud", "earnings manipulation", "accounting", "financial misstatement",
        "false reporting", "misappropriation",
    )),
    ("regulatory", (
        "finra", "sec charge", "sec fined", "regulator", "regulatory", "enforcement",
        "compliance", "aml", "kyc", "due diligence", "penalty", "fine", "fined",
        "censure", "cease and desist", "consent order", "disciplinary", "license",
        "permit", "audit", "disclosure", "antitrust", "probe", "investigation",
        "customs fraud", "trade fraud", "tariff", "import violation", "export violation",
        "governance failure", "internal control", "operational risk", "systemic risk",
    )),
    ("legal_reputational", (
        "lawsuit", "litigation", "court", "settlement", "class action", "misconduct",
        "scandal", "whistleblower", "defamation", "boycott", "controversy", "negligence",
        "malpractice", "cover-up", "cover up", "reputation", "reputational", "harassment",
        "discrimination", "ethical", "wrongdoing", "conflict of interest", "nepotism",
        "favoritism", "abuse of power", "product recall", "recall", "defective",
        "unsafe product", "food safety", "contamination", "health hazard", "pollution",
        "environmental", "illegal dumping", "worker abuse", "wage theft", "unsafe working",
        "labor violation", "labour violation", "privacy violation", "data misuse",
        "adverse media", "negative media", "negative news", "allegation", "indictment",
        "conviction", "arrest", "prosecution", "charges", "conspiracy", "scheme", "scam",
        "misrepresentation", "deception", "falsification", "forged", "forgery",
        "counterfeit", "piracy", "espionage", "cybercrime", "cyber attack", "cyberattack",
        "hacking", "data breach", "ransomware", "malware", "phishing", "identity theft",
        "insolvency", "bankruptcy", "default",
    )),
]

# Raw vocabulary (deduplicated on load).
_RAW_TERMS: list[str] = [
    "financial crime", "money laundering", "terrorism", "terrorist financing",
    "extremism", "violent extremism", "radicalization", "sanctions violation",
    "sanctions evasion", "fraud", "financial fraud", "bank fraud", "insurance fraud",
    "tax fraud", "securities fraud", "investment fraud", "accounting fraud",
    "wire fraud", "credit card fraud", "identity theft", "identity fraud",
    "embezzlement", "bribery", "corruption", "political corruption",
    "government corruption", "kickback", "graft", "extortion", "blackmail",
    "racketeering", "organized crime", "criminal organization", "criminal network",
    "crime syndicate", "mafia", "cartel", "drug trafficking", "narcotics trafficking",
    "human trafficking", "human smuggling", "forced labor", "modern slavery",
    "child exploitation", "child trafficking", "sexual exploitation", "cybercrime",
    "cyber attack", "hacking", "data breach", "security breach", "ransomware",
    "malware", "spyware", "phishing", "social engineering", "credential theft",
    "account takeover", "computer intrusion", "network intrusion", "digital fraud",
    "online scam", "internet fraud", "dark web", "illegal marketplace",
    "counterfeiting", "counterfeit goods", "fake products", "forged documents",
    "document fraud", "identity forgery", "currency counterfeit", "piracy",
    "copyright infringement", "trademark infringement", "intellectual property theft",
    "trade secret theft", "industrial espionage", "espionage", "corporate espionage",
    "insider trading", "market manipulation", "price manipulation", "stock manipulation",
    "securities violation", "regulatory violation", "compliance violation",
    "legal violation", "criminal investigation", "criminal charges", "indictment",
    "conviction", "arrest", "prosecution", "lawsuit", "litigation", "court case",
    "criminal case", "civil lawsuit", "class action lawsuit", "settlement", "penalty",
    "fine", "regulatory action", "enforcement action", "investigation", "probe",
    "audit failure", "compliance failure", "risk exposure", "reputational risk",
    "brand damage", "public scandal", "controversy", "misconduct", "wrongdoing",
    "ethical violation", "professional misconduct", "employee misconduct",
    "workplace harassment", "sexual harassment", "discrimination", "human rights violation",
    "labor violation", "worker abuse", "unsafe working conditions", "environmental violation",
    "pollution", "illegal dumping", "environmental damage", "deforestation",
    "wildlife trafficking", "illegal fishing", "illegal mining", "conflict minerals",
    "war crimes", "crimes against humanity", "genocide", "ethnic cleansing",
    "armed conflict", "civil war", "insurgency", "rebellion", "coup", "civil unrest",
    "riot", "terror attack", "bombing", "hostage situation", "kidnapping",
    "assassination", "murder", "violent crime", "weapons trafficking", "arms trafficking",
    "illegal weapons", "nuclear proliferation", "chemical weapons", "biological weapons",
    "weapons of mass destruction", "missile proliferation", "arms embargo violation",
    "smuggling", "illegal trade", "black market", "illicit trade", "underground economy",
    "tax evasion", "offshore fraud", "shell company", "shell corporation",
    "beneficial ownership concealment", "hidden assets", "fraudulent transaction",
    "suspicious transaction", "suspicious activity", "money mule", "structuring",
    "smurfing", "illegal proceeds", "criminal proceeds", "dirty money",
    "unexplained wealth", "asset concealment", "asset seizure", "asset freezing",
    "financial misconduct", "bankruptcy fraud", "loan fraud", "mortgage fraud",
    "payment fraud", "invoice fraud", "procurement fraud", "vendor fraud",
    "supplier fraud", "contract fraud", "healthcare fraud", "medicare fraud",
    "benefit fraud", "welfare fraud", "consumer fraud", "investment scam", "ponzi scheme",
    "pyramid scheme", "cryptocurrency fraud", "crypto scam", "crypto laundering",
    "blockchain fraud", "market abuse", "insider dealing", "front running",
    "false reporting", "financial misstatement", "earnings manipulation",
    "accounting irregularity", "corporate fraud", "executive misconduct",
    "fiduciary breach", "conflict of interest", "nepotism", "abuse of power",
    "human rights abuse", "torture", "illegal detention", "political repression",
    "surveillance abuse", "privacy violation", "data misuse", "product safety violation",
    "product recall", "defective product", "unsafe product", "food safety violation",
    "contamination", "health hazard", "medical malpractice", "controlled substance",
    "pharmaceutical fraud", "counterfeit medicine", "medical fraud", "research misconduct",
    "scientific fraud", "data fabrication", "academic fraud", "plagiarism",
    "credential fraud", "immigration fraud", "visa fraud", "passport fraud",
    "smuggling network", "terror cell", "terror network", "extremist group",
    "militant group", "insurgent group", "separatist violence", "radical group",
    "hate group", "hate crime", "religious extremism", "political extremism",
    "online extremism", "extremist propaganda", "recruitment network",
    "foreign terrorist organization", "designated terrorist organization",
    "sanctions list", "blocked entity", "restricted entity", "watchlist", "blacklisted",
    "export violation", "export control violation", "trade restriction",
    "embargo violation", "customs fraud", "trade fraud", "tariff evasion",
    "import violation", "illegal shipment", "smuggled goods", "counterfeit currency",
    "document falsification", "false claims", "misrepresentation", "deception", "scam",
    "conspiracy", "criminal conspiracy", "fraudulent scheme", "illegal operation",
    "unlicensed activity", "license violation", "regulatory breach", "compliance breach",
    "aml violation", "kyc violation", "governance failure", "internal control failure",
    "operational risk", "systemic risk", "bank failure", "corporate collapse",
    "insolvency", "fraudulent bankruptcy", "employee theft", "asset theft",
    "cargo theft", "supply chain crime", "logistics fraud", "procurement corruption",
    "vendor misconduct", "supplier misconduct", "corporate scandal", "executive fraud",
    "public corruption", "bribery scandal", "anti corruption violation",
    "government fraud", "election fraud", "political scandal", "lobbying violation",
    "campaign finance violation", "money laundering investigation",
    "terror financing investigation", "fraud investigation", "corruption investigation",
    "regulatory investigation", "security threat", "national security threat",
    "labor exploitation", "supply chain abuse", "child labor", "worker exploitation",
    "wage theft", "employment fraud", "fake company", "business misconduct",
    "reputation damage", "negative media", "adverse media", "criminal allegations",
    "fraud allegations", "corruption allegations", "misconduct allegations",
    "whistleblower complaint", "regulatory warning", "safety warning", "recall notice",
    "compliance warning",
]


def categorize(term: str) -> str:
    lowered = term.lower()
    for key, triggers in _ROUTES:
        if any(t in lowered for t in triggers):
            return key
    return "legal_reputational"


# Deduplicated term -> category, preserving first occurrence order.
RISK_TERMS: list[str] = list(dict.fromkeys(t.lower() for t in _RAW_TERMS))
TERM_CATEGORY: dict[str, str] = {t: categorize(t) for t in RISK_TERMS}
