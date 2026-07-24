"""String similarity metrics, implemented in pure Python.

Levenshtein and Jaro-Winkler are written out rather than pulled from a
dependency because they *are* the product here - the entity resolution logic
should be inspectable, not a black box behind `pip install`.
"""

from __future__ import annotations


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) < len(b):
        a, b = b, a

    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,        # deletion
                    current[j - 1] + 1,     # insertion
                    previous[j - 1] + (ca != cb),  # substitution
                )
            )
        previous = current
    return previous[-1]


def levenshtein_ratio(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    longest = max(len(a), len(b))
    if longest == 0:
        return 1.0
    return 1.0 - levenshtein(a, b) / longest


def jaro(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0

    match_window = max(len(a), len(b)) // 2 - 1
    if match_window < 0:
        match_window = 0

    a_matched = [False] * len(a)
    b_matched = [False] * len(b)
    matches = 0

    for i, ca in enumerate(a):
        start = max(0, i - match_window)
        end = min(i + match_window + 1, len(b))
        for j in range(start, end):
            if b_matched[j] or b[j] != ca:
                continue
            a_matched[i] = b_matched[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    transpositions = 0
    k = 0
    for i, ca in enumerate(a):
        if not a_matched[i]:
            continue
        while not b_matched[k]:
            k += 1
        if ca != b[k]:
            transpositions += 1
        k += 1
    transpositions //= 2

    return (
        matches / len(a) + matches / len(b) + (matches - transpositions) / matches
    ) / 3.0


def jaro_winkler(a: str, b: str, prefix_weight: float = 0.1) -> float:
    """Jaro with a boost for shared prefixes - company names diverge at the end
    (suffixes, divisions) far more often than at the start."""
    base = jaro(a, b)
    prefix = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        prefix += 1
        if prefix == 4:
            break
    return base + prefix * prefix_weight * (1 - base)


def token_set_ratio(a: str, b: str) -> float:
    """Jaccard overlap of tokens - robust to word reordering."""
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _sorted_tokens(value: str) -> str:
    return " ".join(sorted(value.split()))


def name_similarity(a: str, b: str) -> dict[str, float]:
    """Blend the three views of name similarity into one score.

    Edit distance is measured against both the given order and a token-sorted
    form, keeping the better of the two. Sanctions and registry lists write
    people surname-first ("NASRALLAH, Hasan") while users type them
    forename-first; without this, an exact match scores like a stranger.
    """
    if not a or not b:
        return {"levenshtein": 0.0, "jaro_winkler": 0.0, "token_set": 0.0, "score": 0.0}

    a_sorted, b_sorted = _sorted_tokens(a), _sorted_tokens(b)
    lev = max(levenshtein_ratio(a, b), levenshtein_ratio(a_sorted, b_sorted))
    jw = max(jaro_winkler(a, b), jaro_winkler(a_sorted, b_sorted))
    tok = token_set_ratio(a, b)
    # Token overlap is weighted heaviest: it survives suffix/word-order noise,
    # which is the dominant failure mode across company registries.
    score = 0.25 * lev + 0.35 * jw + 0.40 * tok
    return {
        "levenshtein": round(lev, 4),
        "jaro_winkler": round(jw, 4),
        "token_set": round(tok, 4),
        "score": round(score, 4),
    }
