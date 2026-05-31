"""Shared pytest fixtures and helpers for the test suite.

This module centralizes setup/teardown logic that was previously duplicated
across many test files, most importantly resetting the process-local state in
``app.api.routes`` between tests. Centralizing it keeps tests isolated and
makes the suite easier to maintain and hand over.
"""

from __future__ import annotations

import pytest

from app.api import routes


# Every module-level, process-local container in app.api.routes that holds
# per-job or per-client state. Clearing all of them between tests guarantees
# isolation regardless of which subset a given test happens to touch.
_ROUTE_STATE_ATTRS = (
    "_jobs",
    "_job_status",
    "_job_dirs",
    "_job_progress",
    "_job_owners",
    "_job_locks",
    "_rate_limit",
    "_llm_calls_by_ip",
    "_llm_calls_global",
)


def clear_route_state() -> None:
    """Reset all process-local route state so tests do not leak into each other.

    Safe to call even if an attribute is missing or is a non-dict container;
    ``list``, ``set`` and ``dict`` all support ``.clear()``.
    """
    for attr in _ROUTE_STATE_ATTRS:
        container = getattr(routes, attr, None)
        if container is not None and hasattr(container, "clear"):
            container.clear()


@pytest.fixture()
def reset_route_state():
    """Clear route state before and after a test.

    Use by adding ``reset_route_state`` to a test's parameters when it touches
    upload/job/AI route state but does not build its own app fixture.
    """
    clear_route_state()
    yield
    clear_route_state()
