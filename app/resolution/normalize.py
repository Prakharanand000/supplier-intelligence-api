"""Name / address / domain normalization.

Normalization is the first stage of entity resolution: strip the noise that
differs between registries so the similarity stage compares signal.
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

# Legal-form suffixes. "ABC Manufacturing LLC" and "ABC Manufacturing Ltd" must
# collapse to the same core so name similarity reflects the actual business
# name, not the jurisdiction's incorporation vocabulary.
LEGAL_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "company",
    "llc", "lllp", "llp", "lp", "ltd", "limited", "plc", "pllc",
    "gmbh", "mbh", "ag", "kg", "kgaa", "ug", "se",
    "sa", "sas", "sarl", "sprl", "nv", "bv", "cv", "oy", "ab", "as", "asa",
    "spa", "srl", "sl", "sp", "zoo", "doo", "dd", "ad",
    "pty", "pte", "bhd", "sdn", "kk", "gk",
    "group", "holding", "holdings", "international", "intl",
    "trust", "trustee", "partners", "partnership", "ventures",
}

STOPWORDS = {"the", "and", "of", "for", "de", "la", "el", "y"}

_PUNCT = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WS = re.compile(r"\s+")
# Dotted initialisms: "S.A.", "L.L.C.", "U.S.A." -> "sa", "llc", "usa".
# Must run before punctuation stripping or they shatter into single letters.
_DOTTED = re.compile(r"\b(?:[a-z]\.){2,}", flags=re.IGNORECASE)


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_name(name: str | None) -> str:
    """Lowercase, de-accent, de-punctuate, drop legal suffixes and stopwords."""
    if not name:
        return ""
    value = strip_accents(name).lower()
    value = value.replace("&", " and ")
    value = _DOTTED.sub(lambda m: m.group(0).replace(".", ""), value)
    value = _PUNCT.sub(" ", value)
    tokens = [t for t in _WS.split(value) if t]
    core = [
        t for t in tokens
        if t not in LEGAL_SUFFIXES and t not in STOPWORDS and not t.isdigit()
    ]
    # Never normalize a name out of existence (e.g. "The Group Ltd").
    if not core:
        core = [t for t in tokens if t not in STOPWORDS] or tokens
    return " ".join(core)


def name_tokens(name: str | None) -> set[str]:
    return set(normalize_name(name).split())


def normalize_country(country: str | None) -> str:
    if not country:
        return ""
    value = strip_accents(country).lower().strip()
    value = _DOTTED.sub(lambda m: m.group(0).replace(".", ""), value)
    aliases = {
        "usa": "united states",
        "us": "united states",
        "u s a": "united states",
        "united states of america": "united states",
        "uk": "united kingdom",
        "gb": "united kingdom",
        "great britain": "united kingdom",
        "deutschland": "germany",
        "prc": "china",
        "peoples republic of china": "china",
        "republic of korea": "south korea",
        "uae": "united arab emirates",
    }
    value = _PUNCT.sub(" ", value)
    value = _WS.sub(" ", value).strip()
    return aliases.get(value, value)


def normalize_domain(website: str | None) -> str:
    """Reduce a URL or email to a bare registrable-ish domain."""
    if not website:
        return ""
    value = website.strip().lower()
    if "@" in value and "://" not in value:
        value = value.split("@", 1)[1]
    if "://" not in value:
        value = "http://" + value
    host = urlparse(value).netloc or ""
    host = host.split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def normalize_address(address: str | None) -> str:
    if not address:
        return ""
    value = strip_accents(address).lower()
    value = _PUNCT.sub(" ", value)
    replacements = {
        " street ": " st ", " avenue ": " ave ", " road ": " rd ",
        " boulevard ": " blvd ", " suite ": " ste ", " floor ": " fl ",
        " drive ": " dr ", " parkway ": " pkwy ",
    }
    padded = f" {_WS.sub(' ', value).strip()} "
    for long, short in replacements.items():
        padded = padded.replace(long, short)
    return padded.strip()
