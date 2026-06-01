"""Tests for the redaction layer in app.secrets_manager."""

from __future__ import annotations

from app import secrets_manager as sm


def test_redact_strips_known_secret_value(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-uin-supersecret-123456")
    sm._secrets_cache = {}
    out = sm.redact("oops your sk-uin-supersecret-123456 leaked")
    assert "supersecret" not in out
    assert "***REDACTED***" in out


def test_redact_handles_jwt_pattern():
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NSJ9.AbCdEfGhIjKlMnOp"
    out = sm.redact(f"token={jwt}")
    assert "***REDACTED_JWT***" in out
    assert jwt not in out


def test_redact_handles_authorization_bearer():
    raw = "Authorization: Bearer abcdef1234567890DEADBEEF"
    out = sm.redact(raw)
    assert "Bearer ***REDACTED***" in out
    assert "abcdef1234567890DEADBEEF" not in out


def test_redact_handles_internal_llm_key_prefix():
    raw = "request to gateway used sk-uinABCDEF1234 for auth"
    out = sm.redact(raw)
    assert "***REDACTED_LLM_KEY***" in out
    assert "sk-uinABCDEF1234" not in out


def test_redact_handles_pem_block():
    pem = (
        "-----BEGIN PRIVATE KEY-----\n"
        "MIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQ\n"
        "FAKEKEYDATAFAKEKEYDATAFAKEKEYDATAFAKEKEYDATAFAKE==\n"
        "-----END PRIVATE KEY-----"
    )
    out = sm.redact(f"config={pem} done")
    assert "***REDACTED_PEM***" in out
    assert "FAKEKEYDATA" not in out


def test_redact_handles_api_token_prefix():
    out = sm.redact("X-API-Token: sl_abc123DEF456ghi789JKL")
    assert "***REDACTED_API_TOKEN***" in out
    assert "sl_abc123DEF456ghi789JKL" not in out


def test_redact_does_not_touch_plain_text():
    """Normal log lines must not be redacted."""
    msg = "user uploaded paper.zip with 12 figures and 47 references"
    assert sm.redact(msg) == msg


def test_redact_empty_input():
    assert sm.redact("") == ""
    assert sm.redact(None) is None  # type: ignore[arg-type]
