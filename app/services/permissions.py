"""Permission and session-cookie helpers, extracted from ``app.api.routes``.

These are the **stateless** building blocks of ScholarLint's access
control: share-token parsing, anonymous-session cookie policy, and the
ownership-metadata decision tree. They were the hottest implicit
dependency in the legacy ``routes.py`` god-module — every sibling
router (file_routes / tool_routes / checklist_routes / ai_routes)
indirectly relied on them, but only ``routes.py`` could legally own
the symbols.

By moving the pure functions here we get:

* A single, importable home for permission rules — anyone can
  ``from app.services.permissions import _owner_metadata_allows``
  without poking at the routes module.
* Clear separation between "stateless rule" and "process-bound state":
  this module never touches ``_jobs`` / ``_job_owners`` / ``_job_status``
  / ``_job_dirs``. Anything that needs them stays in ``routes.py``
  (``_require_job_access``, ``_get_report``, ``_get_request_owner``).
* Zero behaviour change. ``routes.py`` re-imports these names so its
  public-within-package surface stays identical.

The async ``_owner_metadata_allows`` helper takes the
``request_owner_loader`` callable as a parameter so it can stay free
of any module-level state. Callers in ``routes.py`` pass
``_get_request_owner`` (which knows how to consult the user / API
token / session-cookie chain).
"""

from __future__ import annotations

import secrets
from typing import Awaitable, Callable

from fastapi import Request, Response

from app.config import settings

# Cookie configuration. Kept here so anyone setting the cookie
# (auth_routes, routes.py owner resolver) goes through the same name
# and TTL.
SESSION_COOKIE_NAME = "sl_session"
SESSION_COOKIE_MAX_AGE = 30 * 86400


# Type alias: an async function that, given (request, response), returns
# the request's logical owner dict. Defined here so the signature shows
# up at a single import site.
RequestOwnerLoader = Callable[[Request, Response | None], Awaitable[dict]]


def request_share_token(request: Request) -> str:
    """Read a share token from query string or request header.

    Returns ``""`` when none is present so callers can compare with
    ``token == ""``. Accepts the URL form (``?share=...``) used by
    e-mailed supervisor links and the header form (``X-Share-Token``)
    used by programmatic clients.
    """
    return (
        request.query_params.get("share")
        or request.headers.get("X-Share-Token")
        or ""
    ).strip()


def secure_session_cookie(request: Request) -> bool:
    """Decide whether the anonymous-session cookie should carry ``Secure``.

    Mirrors ``auth_routes._secure_cookie`` so logged-in and anonymous
    sessions get the same Secure-flag policy:

    * ``True`` when ``settings.app_env`` is ``prod`` / ``production``.
    * ``True`` when the request itself is HTTPS (direct or via the
      ``x-forwarded-proto`` header from a TLS-terminating reverse proxy).
    * ``False`` otherwise (so local plain-HTTP dev sessions are not
      dropped by browsers).
    """
    if settings.app_env in {"prod", "production"}:
        return True
    return (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto", "").lower() == "https"
    )


def set_session_cookie_if_needed(
    response: Response | None,
    session_id: str,
    request: Request | None = None,
) -> None:
    """Persist a generated anonymous session id in an httpOnly cookie.

    Silently no-ops when ``response`` is ``None`` (used by callers that
    only want to read the existing cookie). Secure flag is decided by
    ``secure_session_cookie`` when a ``request`` is supplied.
    """
    if response is None:
        return
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        httponly=True,
        secure=secure_session_cookie(request) if request is not None else False,
        max_age=SESSION_COOKIE_MAX_AGE,
        samesite="lax",
    )


def new_share_token() -> str:
    """Generate a fresh URL-safe share token (~32 chars)."""
    return secrets.token_urlsafe(24)


def owner_metadata(owner: dict, share_token: str | None = None) -> dict:
    """Build the persisted ownership block for a new job.

    ``share_token`` defaults to a freshly generated token so every new
    report has a stable, never-leaked-via-URL share link from day one.
    The session id (when present) is preserved so the report can later
    be reattributed to a logged-in user upgrading from anonymous.
    """
    metadata = {
        "owner_type": owner["owner_type"],
        "owner_id": owner["owner_id"],
        "share_token": share_token or new_share_token(),
    }
    if owner.get("session_id"):
        metadata["session_id"] = owner["session_id"]
    return metadata


def extract_owner_metadata(report_or_metadata) -> dict:
    """Pull a normalized owner dict out of either a report or raw dict.

    Tolerant of missing fields so older / partial payloads do not raise;
    missing values come back as ``None``.
    """
    metadata = getattr(report_or_metadata, "metadata", report_or_metadata) or {}
    return {
        "owner_type": metadata.get("owner_type"),
        "owner_id": metadata.get("owner_id"),
        "session_id": metadata.get("session_id"),
        "share_token": metadata.get("share_token"),
    }


def request_uses_valid_share_token(report, request: Request) -> bool:
    """True if the request carries a share token matching this report.

    Uses ``secrets.compare_digest`` to avoid timing side-channels on the
    token comparison; returns false when either side is missing.
    """
    requested = request_share_token(request)
    share_token = extract_owner_metadata(report).get("share_token")
    if not requested or not share_token:
        return False
    return secrets.compare_digest(requested, str(share_token))


async def owner_metadata_allows(
    metadata: dict,
    request: Request,
    response: Response | None = None,
    *,
    request_owner_loader: RequestOwnerLoader,
    write: bool = False,
    allow_share: bool = True,
) -> bool:
    """Decide whether a request may access a job with the given metadata.

    Decision tree (kept identical to the pre-extraction version):

    1. **Legacy job** (no ``owner_type`` / ``owner_id``): allowed in
       local mode for back-compat with pre-ownership demo reports;
       **denied in production** so a guessed job_id cannot grant access
       (SECURE-S1 / v5.3.91).
    2. **Owner match**: request owner equals the stamped owner →
       full read & write.
    3. **Share token**: when ``allow_share`` is true and a valid share
       token is presented, **read-only** access is granted (writes
       still rejected). Tokens are compared with ``secrets.compare_digest``.
    4. Otherwise: denied.

    ``request_owner_loader`` is injected so this module stays free of
    ``routes.py`` module-level state. Pass ``routes._get_request_owner``
    from the legacy module.
    """
    owner_type = metadata.get("owner_type")
    owner_id = metadata.get("owner_id")
    share_token = metadata.get("share_token")

    # Legacy reports (no ownership stamp) are accessible in local-demo mode
    # but denied in production — see SECURE-S1.
    if not owner_type or not owner_id:
        if settings.app_env in {"prod", "production"}:
            return False
        return True

    request_owner = await request_owner_loader(request, response)
    if request_owner["owner_type"] == owner_type and request_owner["owner_id"] == str(owner_id):
        return True

    requested = request_share_token(request)
    if allow_share and requested and share_token and secrets.compare_digest(requested, str(share_token)):
        return not write

    return False


async def can_access_report(
    report,
    request: Request,
    response: Response | None = None,
    *,
    request_owner_loader: RequestOwnerLoader,
    mode: str = "read",
    allow_share: bool = True,
) -> bool:
    """Convenience wrapper: ask ``owner_metadata_allows`` for a report.

    ``mode`` is ``"read"`` (default) or ``"write"`` — using a string
    keeps call sites readable.
    """
    return await owner_metadata_allows(
        extract_owner_metadata(report),
        request,
        response,
        request_owner_loader=request_owner_loader,
        write=(mode == "write"),
        allow_share=allow_share,
    )
