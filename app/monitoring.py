"""Lightweight in-process request monitoring."""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any


_LONG_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{12,}$")


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_path(path: str) -> str:
    """Avoid leaking job IDs, share tokens, or uploaded file paths in metrics."""
    parts = []
    for part in path.split("/"):
        if not part:
            parts.append(part)
        elif part.isdigit() or _LONG_TOKEN_RE.match(part):
            parts.append("{id}")
        elif "." in part and len(part) > 24:
            parts.append("{file}")
        else:
            parts.append(part)
    return "/".join(parts)


@dataclass
class EndpointStats:
    requests: int = 0
    errors: int = 0
    total_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    last_status: int = 0

    def record(self, status_code: int, latency_ms: float) -> None:
        self.requests += 1
        if status_code >= 500:
            self.errors += 1
        self.total_latency_ms += latency_ms
        self.max_latency_ms = max(self.max_latency_ms, latency_ms)
        self.last_status = status_code

    def snapshot(self, method: str, path: str) -> dict[str, Any]:
        avg_latency_ms = self.total_latency_ms / self.requests if self.requests else 0.0
        return {
            "method": method,
            "path": path,
            "requests": self.requests,
            "errors": self.errors,
            "error_rate": round(self.errors / self.requests, 4) if self.requests else 0.0,
            "avg_latency_ms": round(avg_latency_ms, 2),
            "max_latency_ms": round(self.max_latency_ms, 2),
            "last_status": self.last_status,
        }


class RequestMetrics:
    """Small rolling metrics store for single-process deployments and demos."""

    def __init__(self, recent_size: int = 200) -> None:
        self._recent_size = recent_size
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.started_at = _now_iso()
            self.started_monotonic = time.monotonic()
            self.requests_total = 0
            self.errors_total = 0
            self.total_latency_ms = 0.0
            self.max_latency_ms = 0.0
            self.by_endpoint: dict[tuple[str, str], EndpointStats] = {}
            self.recent: deque[tuple[int, float]] = deque(maxlen=self._recent_size)

    def record(self, method: str, path: str, status_code: int, latency_ms: float) -> None:
        safe_path = _safe_path(path)
        is_error = status_code >= 500
        with self._lock:
            self.requests_total += 1
            if is_error:
                self.errors_total += 1
            self.total_latency_ms += latency_ms
            self.max_latency_ms = max(self.max_latency_ms, latency_ms)
            self.recent.append((status_code, latency_ms))
            key = (method.upper(), safe_path)
            self.by_endpoint.setdefault(key, EndpointStats()).record(status_code, latency_ms)

    def snapshot(self, *, service: str, version: str) -> dict[str, Any]:
        with self._lock:
            recent_count = len(self.recent)
            recent_errors = sum(1 for status, _ in self.recent if status >= 500)
            recent_latency_total = sum(latency for _, latency in self.recent)
            endpoint_rows = [
                stats.snapshot(method, path)
                for (method, path), stats in self.by_endpoint.items()
            ]
            endpoint_rows.sort(key=lambda row: row["requests"], reverse=True)
            avg_latency_ms = self.total_latency_ms / self.requests_total if self.requests_total else 0.0
            return {
                "service": service,
                "version": version,
                "started_at": self.started_at,
                "uptime_seconds": round(time.monotonic() - self.started_monotonic, 2),
                "requests_total": self.requests_total,
                "errors_total": self.errors_total,
                "error_rate": round(self.errors_total / self.requests_total, 4) if self.requests_total else 0.0,
                "avg_latency_ms": round(avg_latency_ms, 2),
                "max_latency_ms": round(self.max_latency_ms, 2),
                "recent_window": {
                    "size": self._recent_size,
                    "requests": recent_count,
                    "errors": recent_errors,
                    "error_rate": round(recent_errors / recent_count, 4) if recent_count else 0.0,
                    "avg_latency_ms": round(recent_latency_total / recent_count, 2) if recent_count else 0.0,
                },
                "endpoints": endpoint_rows[:50],
            }


request_metrics = RequestMetrics()
