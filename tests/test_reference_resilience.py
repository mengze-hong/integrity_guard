"""Tests for reference verification cache and transient failures."""

import asyncio

import pytest

from app.checks import gate_references
from app.checks.gate_references import ReferenceAuthenticityGate
from app.models import BibEntry, Severity


class _Response:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def get(self, *args, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_resolve_doi_caches_successful_metadata():
    client = _FakeClient([
        _Response(200, {"message": {"title": ["Real Paper"]}}),
    ])

    # Per-instance cache (see ReferenceAuthenticityGate.__init__): the gate must
    # cache a successful DOI resolution so the second lookup hits no network.
    gate = ReferenceAuthenticityGate()
    result1 = await gate._resolve_doi("10.1234/real", client, asyncio.Semaphore(1))
    result2 = await gate._resolve_doi("10.1234/real", client, asyncio.Semaphore(1))

    assert result1 == result2
    assert result1[1] == "crossref"
    assert client.calls == 1


@pytest.mark.asyncio
async def test_transient_provider_failures_become_warning_not_fake():
    client = _FakeClient([
        _Response(429),
        _Response(503),
        _Response(500),
    ])
    entry = BibEntry(
        key="rate_limited",
        entry_type="article",
        title="A Real Paper",
        authors=["Jane Doe"],
        year="2024",
        doi="10.1234/temporary",
    )

    issues, meta = await ReferenceAuthenticityGate()._verify_entry(
        entry,
        client,
        asyncio.Semaphore(1),
    )

    assert meta["status"] == "verification_unavailable"
    assert all(issue.severity != Severity.ERROR for issue in issues)
    assert any("暂时无法验证" in issue.message for issue in issues)
