"""Cosine-similarity risk-term matching.

Identifies which controlled risk terms an article expresses, using cosine
similarity between hashed char-ngram vectors (the same offline embedding used by
entity resolution). This catches morphological variants that exact matching
misses - "laundered" against "money laundering", "bribes" against "bribery" -
because char-ngram vectors share sub-word structure.

Speed: a char-trigram inverted index blocks each candidate span to the handful
of terms that could plausibly match, so we never score a span against all ~350
terms.
"""

from __future__ import annotations

import re
from functools import lru_cache

from app.resolution.embeddings import _hashed_vector, cosine
from app.risk.vocabulary import RISK_TERMS, TERM_CATEGORY

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]+")
MATCH_THRESHOLD = 0.72

# Generic business words that partially match multi-word risk terms ("company"
# -> "shell company") but do not, alone, express the risk. A single-word span in
# this set never triggers a term.
_GENERIC_SINGLE = {
    "company", "companies", "group", "firm", "business", "corporate", "corporation",
    "assets", "asset", "claims", "claim", "program", "programme", "activity",
    "activities", "action", "actions", "case", "cases", "report", "reports",
    "risk", "risks", "market", "trade", "staff", "board", "executive", "director",
    "allegation", "allegations", "concern", "concerns", "issue", "issues",
    "practice", "practices", "matter", "matters", "conduct",
}


def _trigrams(text: str) -> set[str]:
    padded = f"  {text.lower()}  "
    return {padded[i:i + 3] for i in range(len(padded) - 2)}


# Precompute term vectors and a trigram -> term-index inverted index. Trigrams
# shared by too many terms (common morphology like "ing", "ion", "ent") are
# non-discriminative and blow up the candidate set, so they are dropped from the
# index - a span still finds its terms through its rarer trigrams.
_MAX_DF = 45
_TERM_VECS = [_hashed_vector(t) for t in RISK_TERMS]
_TRI_INDEX: dict[str, list[int]] = {}
for _i, _term in enumerate(RISK_TERMS):
    for _tri in _trigrams(_term):
        _TRI_INDEX.setdefault(_tri, []).append(_i)
_TRI_INDEX = {tri: idxs for tri, idxs in _TRI_INDEX.items() if len(idxs) <= _MAX_DF}


@lru_cache(maxsize=4096)
def _span_vec(span: str):
    return _hashed_vector(span)


def _spans(text: str) -> list[str]:
    """1- and 2-word windows from the text (deduped). Almost every risk term is
    one or two words; the 2-word window also catches the head of longer terms
    ("export control" -> "export control violation")."""
    words = _WORD.findall(text.lower())
    out: set[str] = set()
    for n in (1, 2):
        for i in range(len(words) - n + 1):
            span = " ".join(words[i:i + n])
            if len(span) >= 4:
                out.add(span)
    return list(out)


@lru_cache(maxsize=1024)
def match_terms(text: str, threshold: float = MATCH_THRESHOLD,
                max_terms: int = 30) -> tuple[dict, ...]:
    """Return the risk terms expressed in `text`, best cosine first.

    Cached: demo article bodies are static, so repeat lookups are free.
    Returns a tuple so the lru_cache result is immutable.
    """
    if not text:
        return ()

    best: dict[int, tuple[float, str]] = {}
    for span in _spans(text):
        if " " not in span and span in _GENERIC_SINGLE:
            continue
        sv = _span_vec(span)
        candidates: set[int] = set()
        for tri in _trigrams(span):
            candidates.update(_TRI_INDEX.get(tri, ()))
        # Each span expresses at most one term - its best cosine match - so
        # "trafficking" resolves to one term, not every trafficking variant.
        top_ti, top_score = None, threshold
        for ti in candidates:
            score = cosine(sv, _TERM_VECS[ti])
            if score >= top_score:
                top_ti, top_score = ti, score
        if top_ti is not None and top_score > best.get(top_ti, (0.0, ""))[0]:
            best[top_ti] = (top_score, span)

    results = [
        {
            "term": RISK_TERMS[ti],
            "category": TERM_CATEGORY[RISK_TERMS[ti]],
            "score": round(score, 3),
            "matched_span": span,
        }
        for ti, (score, span) in best.items()
    ]
    results.sort(key=lambda r: r["score"], reverse=True)
    return tuple(results[:max_terms])
