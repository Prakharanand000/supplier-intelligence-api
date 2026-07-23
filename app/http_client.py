"""Shared async HTTP layer: identity headers, per-host rate limits, retries,
and a PostgreSQL-backed response cache.

Every outbound call in this project goes through `fetch()`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import delete, select

from app.config import settings
from app.db import session_factory
from app.models import HttpCache

log = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None
_host_locks: dict[str, asyncio.Lock] = {}
_host_last_call: dict[str, float] = {}


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(25.0, connect=10.0),
            follow_redirects=True,
            headers={
                "User-Agent": settings.user_agent,
                "Accept-Encoding": "gzip, deflate",
            },
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _throttle(host: str) -> None:
    """Enforce the configured minimum interval between calls to a host."""
    rate = settings.rate_limits.get(host)
    if not rate:
        return
    min_interval = 1.0 / rate
    lock = _host_locks.setdefault(host, asyncio.Lock())
    async with lock:
        last = _host_last_call.get(host, 0.0)
        wait = min_interval - (time.monotonic() - last)
        if wait > 0:
            await asyncio.sleep(wait)
        _host_last_call[host] = time.monotonic()


def _cache_key(method: str, url: str, params: dict | None) -> str:
    raw = f"{method}|{url}|{json.dumps(params or {}, sort_keys=True)}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def _cache_get(key: str, ttl_hours: int) -> str | None:
    async with session_factory()() as db:
        row = (
            await db.execute(select(HttpCache).where(HttpCache.cache_key == key))
        ).scalar_one_or_none()
        if row is None:
            return None
        fetched = row.fetched_at
        if fetched.tzinfo is None:  # SQLite returns naive datetimes
            fetched = fetched.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - fetched > timedelta(hours=ttl_hours):
            return None
        return row.body


async def _cache_put(key: str, url: str, status: int, body: str) -> None:
    async with session_factory()() as db:
        await db.execute(delete(HttpCache).where(HttpCache.cache_key == key))
        db.add(
            HttpCache(cache_key=key, url=url, status_code=status, body=body)
        )
        await db.commit()


async def fetch(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    method: str = "GET",
    ttl_hours: int | None = None,
    retries: int = 3,
    use_cache: bool = True,
    expect_missing: bool = False,
) -> str | None:
    """Fetch a URL as text. Returns None on persistent failure.

    Sources are expected to degrade gracefully: one dead upstream must not
    fail the whole investigation.
    """
    ttl = settings.http_cache_ttl_hours if ttl_hours is None else ttl_hours
    key = _cache_key(method, url, params)

    if use_cache:
        cached = await _cache_get(key, ttl)
        if cached is not None:
            log.debug("cache hit %s", url)
            return cached

    host = urlparse(url).netloc
    client = get_client()
    backoff = 1.0

    # A 429 needs a real cooldown, not the generic exponential ramp - GDELT in
    # particular enforces a multi-second window per client IP.
    throttled_backoff = 8.0

    for attempt in range(1, retries + 1):
        await _throttle(host)
        try:
            resp = await client.request(method, url, params=params, headers=headers)
            if resp.status_code == 429:
                backoff = max(backoff, throttled_backoff)
                retry_after = resp.headers.get("retry-after")
                if retry_after and retry_after.isdigit():
                    backoff = max(backoff, float(retry_after))
                raise httpx.HTTPStatusError(
                    "rate limited (429)", request=resp.request, response=resp
                )
            if resp.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"retryable status {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
            if resp.status_code >= 400:
                # A 404 on an optional lookup (e.g. "does this LEI have a
                # parent?") is a legitimate answer, not a fault.
                if resp.status_code == 404 and expect_missing:
                    log.debug("%s -> 404 (no such record)", url)
                else:
                    log.warning("%s -> HTTP %s (not retrying)", url, resp.status_code)
                return None
            body = resp.text
            if use_cache:
                await _cache_put(key, str(resp.url), resp.status_code, body)
            return body
        except Exception as exc:  # noqa: BLE001 - network layer is best-effort
            if attempt == retries:
                log.warning("%s failed after %s attempts: %s", url, retries, exc)
                return None
            await asyncio.sleep(backoff)
            backoff *= 2
    return None


async def fetch_json(url: str, **kwargs: Any) -> Any | None:
    body = await fetch(url, **kwargs)
    if body is None:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        log.warning("%s returned non-JSON body", url)
        return None
