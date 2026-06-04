"""Lightweight counters for API HTTP statuses during one parser run."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class ApiMetrics:
    status_counts: Counter[int] = field(default_factory=Counter)
    method_status_counts: Counter[tuple[str, int]] = field(default_factory=Counter)

    def record(self, method: str, status_code: int | str | None) -> None:
        try:
            status = int(status_code or 0)
        except (TypeError, ValueError):
            status = 0
        if status <= 0:
            return
        self.status_counts[status] += 1
        self.method_status_counts[(method or "unknown", status)] += 1

    def reset(self) -> None:
        self.status_counts.clear()
        self.method_status_counts.clear()

    def has_data(self) -> bool:
        return bool(self.status_counts)

    def status_summary(self) -> str:
        return ", ".join(
            f"{status}={count}" for status, count in sorted(self.status_counts.items())
        )

    def error_summary(self) -> str:
        error_counts = {
            status: count
            for status, count in sorted(self.status_counts.items())
            if status >= 400
        }
        if not error_counts:
            return "нет"
        return ", ".join(f"{status}={count}" for status, count in error_counts.items())


API_METRICS = ApiMetrics()


def record_api_status(method: str, status_code: int | str | None) -> None:
    API_METRICS.record(method, status_code)


def reset_api_metrics() -> None:
    API_METRICS.reset()
