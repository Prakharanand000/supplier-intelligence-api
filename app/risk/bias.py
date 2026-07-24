"""Media objectivity / bias analysis.

Adverse-media screening has a quality problem: a sober regulatory filing and a
sensationalist opinion piece both surface as "negative news", but they do not
deserve the same weight. This module scores how *factual* an article reads and
flags the specific lines where subjective, loaded or unverified language
appears, so an analyst can separate reporting from editorialising.

It is a transparent lexicon-and-rule model, not an ML classifier: every flag
points at the exact words that triggered it, which is what makes the output
defensible.
"""

from __future__ import annotations

import re

# Each lexicon maps a bias type to its trigger terms and a weight. Weight is how
# strongly a hit pushes an article toward "polarized".
LEXICONS: dict[str, dict] = {
    "loaded_language": {
        "label": "Loaded / emotional language",
        "weight": 1.0,
        "terms": [
            "shocking", "outrageous", "disgraceful", "scandalous", "damning",
            "explosive", "bombshell", "devastating", "catastrophic", "reckless",
            "brazen", "egregious", "notorious", "infamous", "crooked", "shady",
            "sinister", "sordid", "appalling", "disturbing", "alarming",
            "staggering", "jaw-dropping", "horrifying", "grotesque", "vile",
        ],
    },
    "absolutes": {
        "label": "Absolutes / overgeneralisation",
        "weight": 0.8,
        "terms": [
            "worst", "never", "always", "everyone knows", "no one",
            "completely", "totally", "utterly", "unprecedented", "everybody",
            "nobody", "without exception", "every single", "guaranteed",
        ],
    },
    "unverified": {
        "label": "Unverified attribution",
        "weight": 0.9,
        "terms": [
            "reportedly", "sources say", "sources claim", "insiders say",
            "insiders claim", "rumored", "rumoured", "it is believed",
            "some say", "critics say", "many believe", "widely believed",
            "anonymous sources", "word on the street", "speculation",
        ],
    },
    "opinion": {
        "label": "Opinion asserted as fact",
        "weight": 0.85,
        "terms": [
            "clearly", "obviously", "undoubtedly", "of course", "everyone agrees",
            "any reasonable person", "make no mistake", "let us be clear",
            "the truth is", "plain and simple", "beyond question",
        ],
    },
    "editorializing": {
        "label": "Charged reporting verbs",
        "weight": 0.75,
        "terms": [
            "slammed", "blasted", "lashed out", "railed against", "decried",
            "torched", "eviscerated", "ripped into", "hammered", "skewered",
            "unleashed", "erupted", "fumed", "raged",
        ],
    },
}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")

# Precompiled word-boundary matchers, longest term first so multi-word phrases
# win over their component words.
_MATCHERS: list[tuple[str, str, re.Pattern]] = []
for _bias_type, _spec in LEXICONS.items():
    for _term in sorted(_spec["terms"], key=len, reverse=True):
        _MATCHERS.append(
            (_bias_type, _term, re.compile(r"\b" + re.escape(_term) + r"\b", re.I))
        )

POLARIZED_THRESHOLD = 0.45
MIXED_THRESHOLD = 0.18


def split_sentences(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def _spans_for(sentence: str) -> tuple[list[dict], dict[str, list[str]]]:
    """Return highlight spans and the terms matched, grouped by bias type."""
    raw: list[tuple[int, int, str]] = []
    by_type: dict[str, list[str]] = {}

    for bias_type, term, pattern in _MATCHERS:
        for m in pattern.finditer(sentence):
            raw.append((m.start(), m.end(), bias_type))
            by_type.setdefault(bias_type, [])
            if sentence[m.start():m.end()] not in by_type[bias_type]:
                by_type[bias_type].append(sentence[m.start():m.end()])

    if not raw:
        return [], {}

    # Merge overlapping spans (a phrase and a contained word), keeping the
    # highest-weight type for the merged range.
    raw.sort()
    merged: list[dict] = []
    for start, end, btype in raw:
        if merged and start <= merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], end)
            if LEXICONS[btype]["weight"] > LEXICONS[merged[-1]["type"]]["weight"]:
                merged[-1]["type"] = btype
        else:
            merged.append({"start": start, "end": end, "type": btype})
    return merged, by_type


def analyze(text: str) -> dict:
    """Score the objectivity of an article body and flag biased sentences."""
    sentences = split_sentences(text)
    if not sentences:
        return {
            "label": "Unrated",
            "score": 0.0,
            "flagged_count": 0,
            "total_sentences": 0,
            "bias_types": [],
            "sentences": [],
        }

    analyzed: list[dict] = []
    weight_total = 0.0
    type_counts: dict[str, int] = {}

    for sentence in sentences:
        spans, by_type = _spans_for(sentence)
        if by_type:
            weight_total += max(LEXICONS[t]["weight"] for t in by_type)
            for btype in by_type:
                type_counts[btype] = type_counts.get(btype, 0) + 1
            reasons = [
                {"type": t, "label": LEXICONS[t]["label"], "terms": terms}
                for t, terms in by_type.items()
            ]
        else:
            reasons = []
        analyzed.append(
            {
                "text": sentence,
                "biased": bool(by_type),
                "spans": spans,
                "reasons": reasons,
            }
        )

    flagged = sum(1 for s in analyzed if s["biased"])
    flagged_ratio = flagged / len(sentences)
    # Weighted density: intensity spread over ALL sentences, so a single hedge
    # in an otherwise sober article stays "Mixed" rather than jumping to
    # "Polarized". Only sustained loaded language pushes the score high.
    weighted_density = weight_total / len(sentences)
    score = round(min(1.0, 0.5 * flagged_ratio + 0.5 * weighted_density), 3)

    if score >= POLARIZED_THRESHOLD:
        label = "Polarized"
    elif score >= MIXED_THRESHOLD:
        label = "Mixed"
    else:
        label = "Factual"

    bias_types = [
        {"type": t, "label": LEXICONS[t]["label"], "count": c}
        for t, c in sorted(type_counts.items(), key=lambda kv: kv[1], reverse=True)
    ]

    return {
        "label": label,
        "score": score,
        "flagged_count": flagged,
        "total_sentences": len(sentences),
        "bias_types": bias_types,
        "sentences": analyzed,
    }
