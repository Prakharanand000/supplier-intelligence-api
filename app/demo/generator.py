"""Deterministic generator for the demo watchlist.

Produces ~17 additional fictional entities (companies and individuals) with
10-15 adverse-media articles each, so the dashboard, word cloud and cosine
matcher have a rich corpus to work on. Every entity is invented; real
organisations are never given fabricated allegations.

Articles are composed from templates keyed to the five risk categories, with a
deliberate factual / mixed / polarized tone spread. All choices are derived
from indices, so the corpus is identical on every build.
"""

from __future__ import annotations

# (name, type, country, sector, slug)
ENTITY_SPECS: list[tuple[str, str, str, str]] = [
    ("Atlas Global Bank", "organization", "United States", "Banking"),
    ("Sterling Meridian Financial", "organization", "United Kingdom", "Financial services"),
    ("Cobalt Trade Partners", "organization", "Singapore", "Commodities"),
    ("Nordvik Energy AS", "organization", "Norway", "Energy"),
    ("Zenith Capital Group", "organization", "United States", "Asset management"),
    ("Silk Road Commodities Ltd", "organization", "United Arab Emirates", "Trading"),
    ("Pinnacle Asset Management", "organization", "United States", "Asset management"),
    ("Orion Shipping Lines", "organization", "Greece", "Logistics"),
    ("Vanguard Mercantile Corp", "organization", "United States", "Trade finance"),
    ("Aurora Fintech Holdings", "organization", "Estonia", "Fintech"),
    ("Redwood Pharma Industries", "organization", "India", "Pharmaceuticals"),
    ("Continental Freight Group", "organization", "Germany", "Logistics"),
    ("Summit Precious Metals", "organization", "South Africa", "Mining"),
    ("Viktor Ashford", "individual", "United Kingdom", "Financier"),
    ("Elena Marchetti", "individual", "Italy", "Executive"),
    ("Dmitri Volkov", "individual", "Cyprus", "Investor"),
    ("Rashid Al-Mansoori", "individual", "United Arab Emirates", "Trader"),
]

# Headline-friendly risk terms per category (drawn from the controlled vocabulary).
CATEGORY_TERMS: dict[str, list[str]] = {
    "financial_crime": ["money laundering", "securities fraud", "embezzlement",
                        "bribery", "insider trading", "wire fraud", "tax evasion",
                        "accounting fraud", "market manipulation"],
    "legal_reputational": ["a class action lawsuit", "serious misconduct",
                          "a corporate scandal", "a whistleblower complaint",
                          "gross negligence", "a conflict of interest",
                          "a major data breach", "a product recall"],
    "regulatory": ["a FINRA enforcement action", "SEC charges", "a compliance failure",
                  "a consent order", "a regulatory penalty", "an audit failure",
                  "a disclosure violation", "an antitrust probe"],
    "terrorism_serious_crime": ["arms trafficking", "human trafficking",
                               "drug trafficking", "smuggling", "organized crime",
                               "racketeering", "forced labor"],
    "sanctions": ["sanctions evasion", "an export control violation",
                 "an OFAC designation", "an embargo violation",
                 "watchlist exposure", "an asset freeze"],
}
CAT_CYCLE = ["financial_crime", "legal_reputational", "regulatory",
             "terrorism_serious_crime", "sanctions"]

REGULATORS = ["The SEC", "FINRA", "A federal regulator", "The Department of Justice",
              "A state regulator", "The Financial Conduct Authority", "Prosecutors"]

# tone -> (title, body) templates. {e}=entity, {t}=term, {reg}=regulator, {k}=kind noun.
TEMPLATES: dict[str, list[tuple[str, str]]] = {
    "factual": [
        ("{reg} penalises {e} over {t}",
         "{reg} penalised {e} in connection with {t}. The {k} said it has strengthened its "
         "controls and is cooperating with authorities. No individuals were charged."),
        ("{e} discloses investigation into {t}",
         "{e} disclosed that it is the subject of an investigation relating to {t}. The {k} "
         "said it is cooperating fully and contests any wrongdoing. A hearing is expected next quarter."),
        ("{e} settles {t} allegations",
         "{e} agreed to settle allegations of {t} for an undisclosed sum. The settlement "
         "resolves a multi-year inquiry. The {k} said the conduct violated its own policies."),
        ("Court filing names {e} in {t} case",
         "A court filing named {e} in a matter concerning {t}. The {k} declined to comment "
         "on ongoing litigation. Proceedings continue in a federal court."),
        ("Regulator opens review of {e} over {t}",
         "A regulator opened a review of {e} over {t}. The {k} agreed to a remediation plan "
         "and independent monitoring. An auditor will report quarterly."),
    ],
    "mixed": [
        ("{e} executive departs amid {t} claims",
         "A senior figure at {e} departed amid claims of {t}. Some say the exit was overdue. "
         "The {k} thanked the executive for years of service and said controls remain robust."),
        ("Questions mount over {e} and {t}",
         "Questions are mounting over {e}'s exposure to {t}. Many believe regulators will act "
         "before year-end. The {k} said it takes the concerns seriously and is reviewing them."),
    ],
    "polarized": [
        ("Shocking: {e}'s alleged {t} exposed",
         "In a truly shocking development, sources say {e} was brazenly involved in {t}. "
         "Everyone knows this is only the beginning. Critics say the {k} is rotten to the core."),
        ("Damning claims link {e} to {t}",
         "Damning new claims allege {e} orchestrated {t}. Word on the street is that the scale "
         "is staggering and that nobody at the top can be trusted. It is, frankly, appalling."),
        ("Make no mistake: {e}'s {t} is the worst yet",
         "Make no mistake, the {t} at {e} is obviously the worst this industry has ever seen. "
         "Any reasonable person can see the truth. The whole outfit looks utterly reckless."),
    ],
}
TONE_CYCLE = ["factual", "factual", "polarized", "factual", "mixed",
              "factual", "polarized", "factual", "factual", "mixed",
              "factual", "polarized", "factual", "factual", "factual"]

SOURCES = {
    "factual": ["Reuters", "Bloomberg", "Financial Times", "Associated Press",
                "Compliance Weekly", "Regional Wire"],
    "mixed": ["City Gazette", "Investor Post"],
    "polarized": ["The Daily Ledger", "National Tribune", "The Street Whisper"],
}
MONTHS = [f"{y}-{m:02d}-{(d % 27) + 1:02d}"
          for y in (2026, 2025, 2024) for m, d in zip(range(12, 0, -1), range(3, 40, 3))]


def _slug(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _kind(etype: str) -> str:
    return "individual" if etype == "individual" else "firm"


def _article(entity: str, etype: str, ci: int, ki: int) -> dict:
    cat = CAT_CYCLE[(ci + ki) % len(CAT_CYCLE)]
    term = CATEGORY_TERMS[cat][(ci * 2 + ki) % len(CATEGORY_TERMS[cat])]
    tone = TONE_CYCLE[ki % len(TONE_CYCLE)]
    tpl_title, tpl_body = TEMPLATES[tone][(ci + ki) % len(TEMPLATES[tone])]
    reg = REGULATORS[(ci + ki) % len(REGULATORS)]
    src = SOURCES[tone][(ci + ki) % len(SOURCES[tone])]
    date = MONTHS[(ci * 3 + ki) % len(MONTHS)]
    fill = {"e": entity, "t": term, "reg": reg, "k": _kind(etype)}
    # Title case the term when it opens the headline.
    title = tpl_title.format(**{**fill, "t": term.lstrip("a ").replace("an ", "")})
    return {"subject": _slug(entity), "source": src, "date": date,
            "title": title, "body": tpl_body.format(**fill)}


def _subject_meta(name: str, etype: str, country: str, sector: str, idx: int) -> dict:
    slug = _slug(name)
    is_org = etype == "organization"
    conf = 0.7 + (idx % 5) * 0.05
    return {
        "name": name, "entity_type": etype, "country": country,
        "website": (slug.replace("-", "") + ".example") if is_org else None,
        "aliases": [f"{name.split()[0]} {sector}"] if is_org else [],
        "registration": f"REG-{9000 + idx}", "lei": f"5493DEMO{idx:04d}GEN00" if is_org else None,
        "cik": None, "identity_confidence": round(conf, 2),
        "status": "verified" if conf >= 0.8 else "probable",
        "tagline": f"{sector} · {country}",
        "sanctions_list_size": 39564,
        "litigation": [
            {"case": f"In re {name} Litigation", "court": "Federal Court",
             "date": MONTHS[idx % len(MONTHS)], "confidence": 0.8, "url": None,
             "nature_of_suit": sector}
        ],
        "ownership": ([
            {"name": f"{name.split()[0]} Holdings Ltd", "role": "Parent",
             "relationship_type": "ultimate_parent", "country": country, "confidence": 0.82},
            {"name": f"{'Alex' if idx % 2 else 'Jordan'} Keller", "role": "Chief Executive Officer",
             "relationship_type": "officer_or_director", "confidence": 0.78},
        ] if is_org else []),
        "transactions": [],
        "alternatives": [
            {"name": f"{name} International", "source": "GLEIF", "confidence": 0.55,
             "confidence_breakdown": {"name": 0.68, "embedding": 0.5, "address": 0.0}},
        ],
    }


def build() -> tuple[dict, list[dict]]:
    subjects: dict[str, dict] = {}
    articles: list[dict] = []
    for idx, (name, etype, country, sector) in enumerate(ENTITY_SPECS):
        slug = _slug(name)
        subjects[slug] = _subject_meta(name, etype, country, sector, idx)
        count = 10 + (idx % 6)  # 10-15 articles
        for ki in range(count):
            articles.append(_article(name, etype, idx, ki))
    return subjects, articles


GEN_SUBJECTS, GEN_ARTICLES = build()
