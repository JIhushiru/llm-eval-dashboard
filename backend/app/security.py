"""Shared-token auth gate.

A single opt-in bearer token protects the write/read API surface. It is a
coarse gate suitable for putting the local tool behind a shared secret — not
per-user auth. Disabled (open) when `EVALFORGE_API_TOKEN` is unset/empty, which
keeps local dev, the seed script, and the test suite working with no config.
"""

import secrets

from fastapi import HTTPException, Request

from app.config import get_settings


def _extract_token(request: Request) -> str | None:
    """Prefer `Authorization: Bearer <token>`; fall back to `?token=` for the
    plain-anchor export download links, which cannot set request headers."""
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.query_params.get("token")


def require_token(request: Request) -> None:
    """Router dependency: 401 unless a valid token is presented (no-op when the
    gate is disabled)."""
    expected = get_settings().evalforge_api_token
    if not expected:
        return
    provided = _extract_token(request)
    # Compare on bytes: secrets.compare_digest raises TypeError on str inputs
    # containing non-ASCII characters, which would otherwise surface as a 500
    # for an unauthenticated request presenting e.g. `?token=café`.
    if not provided or not secrets.compare_digest(
        provided.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(
            status_code=401,
            detail="missing or invalid API token",
            headers={"WWW-Authenticate": "Bearer"},
        )
