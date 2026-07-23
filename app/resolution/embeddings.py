"""Embedding backends for semantic name/description similarity.

Priority: OpenAI text-embedding-3-large -> sentence-transformers MiniLM ->
a pure-python hashed char-ngram TF-IDF vector.

The last one exists so entity resolution works with no paid API and no model
download. It is weaker than a real embedding model but is deterministic,
dependency-free, and captures sub-word overlap that plain edit distance misses.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
from collections import Counter

from app.config import settings

log = logging.getLogger(__name__)

_backend: str | None = None
_local_model = None
_openai_client = None

_HASH_DIM = 512
_NGRAM = 3
_WS = re.compile(r"\s+")


# --------------------------------------------------------------------------
# Backend 3: hashed char-ngram TF-IDF (always available)
# --------------------------------------------------------------------------
def _hashed_vector(text: str) -> list[float]:
    cleaned = _WS.sub(" ", (text or "").lower()).strip()
    if not cleaned:
        return [0.0] * _HASH_DIM
    padded = f"  {cleaned}  "
    grams = [padded[i : i + _NGRAM] for i in range(len(padded) - _NGRAM + 1)]
    counts = Counter(grams)

    vec = [0.0] * _HASH_DIM
    for gram, count in counts.items():
        idx = hash_ngram(gram) % _HASH_DIM
        # Sublinear tf damps the effect of long repetitive strings.
        vec[idx] += 1.0 + math.log(count)

    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def hash_ngram(gram: str) -> int:
    """Stable (non-salted) hash - Python's builtin hash() is randomized per
    process, which would make vectors non-reproducible across restarts."""
    h = 2166136261
    for ch in gram:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


# --------------------------------------------------------------------------
# Backend selection
# --------------------------------------------------------------------------
def _resolve_backend() -> str:
    global _backend, _local_model, _openai_client
    if _backend is not None:
        return _backend

    want = settings.embedding_backend.lower()

    if want in ("auto", "openai") and settings.openai_api_key:
        try:
            from openai import AsyncOpenAI

            _openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
            _backend = "openai"
            log.info("Embeddings: OpenAI text-embedding-3-large")
            return _backend
        except Exception as exc:  # noqa: BLE001
            log.warning("OpenAI embeddings unavailable (%s)", exc)

    if want in ("auto", "local"):
        try:
            from sentence_transformers import SentenceTransformer

            _local_model = SentenceTransformer("all-MiniLM-L6-v2")
            _backend = "local"
            log.info("Embeddings: sentence-transformers/all-MiniLM-L6-v2")
            return _backend
        except Exception as exc:  # noqa: BLE001
            log.info("sentence-transformers unavailable (%s)", exc)

    _backend = "hashed"
    log.info("Embeddings: pure-python hashed char-ngram TF-IDF")
    return _backend


def active_backend() -> str:
    return _resolve_backend()


async def embed(texts: list[str]) -> list[list[float]]:
    backend = _resolve_backend()
    cleaned = [t or "" for t in texts]

    if backend == "openai":
        try:
            resp = await _openai_client.embeddings.create(
                model="text-embedding-3-large", input=cleaned
            )
            return [d.embedding for d in resp.data]
        except Exception as exc:  # noqa: BLE001
            log.warning("OpenAI embedding call failed, using hashed: %s", exc)
            return [_hashed_vector(t) for t in cleaned]

    if backend == "local":
        def _run() -> list[list[float]]:
            vectors = _local_model.encode(cleaned, normalize_embeddings=True)
            return [list(map(float, v)) for v in vectors]

        return await asyncio.to_thread(_run)

    return [_hashed_vector(t) for t in cleaned]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


async def similarity(a: str, b: str) -> float:
    vectors = await embed([a, b])
    return cosine(vectors[0], vectors[1])
