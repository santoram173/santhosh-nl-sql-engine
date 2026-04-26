"""In-memory metrics collector."""
from __future__ import annotations
from collections import defaultdict
from typing import Optional
import threading


class MetricsCollector:
    _instance: Optional["MetricsCollector"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.total_queries = 0
        self.successful_queries = 0
        self.failed_queries = 0
        self.blocked_queries = 0
        self.total_latency_ms = 0.0
        self.stage_block_counts: dict[str, int] = defaultdict(int)

    @classmethod
    def get_instance(cls) -> "MetricsCollector":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def record_query_start(self):
        with self._lock:
            self.total_queries += 1

    def record_success(self, latency_ms: float):
        with self._lock:
            self.successful_queries += 1
            self.total_latency_ms += latency_ms

    def record_failed(self):
        with self._lock:
            self.failed_queries += 1

    def record_blocked(self, stage: str):
        with self._lock:
            self.blocked_queries += 1
            self.stage_block_counts[stage] += 1

    def to_dict(self) -> dict:
        with self._lock:
            success_rate = round(
                (self.successful_queries / self.total_queries * 100) if self.total_queries else 0,
                1,
            )
            avg_lat = round(
                self.total_latency_ms / self.successful_queries if self.successful_queries else 0,
                1,
            )
            return {
                "total_queries": self.total_queries,
                "successful_queries": self.successful_queries,
                "failed_queries": self.failed_queries,
                "blocked_queries": self.blocked_queries,
                "success_rate": success_rate,
                "avg_latency_ms": avg_lat,
                "stage_block_counts": dict(self.stage_block_counts),
            }
