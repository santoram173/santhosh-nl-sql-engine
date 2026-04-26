"""Admin endpoints: /admin/metrics and /admin/logs."""
import logging
import datetime
from collections import deque
from fastapi import APIRouter, Query
from backend.models.schemas import MetricsResponse, LogsResponse, LogEntry
from backend.services.metrics import MetricsCollector
from backend.services.gemini import GeminiProvider

log = logging.getLogger(__name__)
router = APIRouter()

# In-memory log ring buffer (last 500 entries)
_log_buffer: deque[dict] = deque(maxlen=500)


class RingBufferHandler(logging.Handler):
    """Logging handler that appends to the in-memory ring buffer."""
    def emit(self, record: logging.LogRecord):
        _log_buffer.append({
            "timestamp": datetime.datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "message": self.format(record),
            "extra": {"logger": record.name},
        })


# Register handler on root logger at import time
_handler = RingBufferHandler()
_handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
logging.getLogger().addHandler(_handler)


@router.get("/metrics", response_model=MetricsResponse, summary="Engine metrics")
async def get_metrics() -> MetricsResponse:
    """
    Returns aggregate metrics for the query engine:
    - Total, successful, blocked, and failed query counts
    - Success rate and average latency
    - Per-stage block counts (which stages are rejecting most queries)
    """
    m = MetricsCollector.get_instance().to_dict()
    gemini_stats = GeminiProvider.get_instance().stats

    return MetricsResponse(
        total_queries=m["total_queries"],
        successful_queries=m["successful_queries"],
        blocked_queries=m["blocked_queries"],
        failed_queries=m["failed_queries"],
        success_rate=m["success_rate"],
        avg_latency_ms=m["avg_latency_ms"],
        stage_block_counts=m["stage_block_counts"],
    )


@router.get("/logs", response_model=LogsResponse, summary="Recent application logs")
async def get_logs(
    limit: int = Query(default=50, le=500, description="Number of log entries to return"),
    level: str = Query(default="", description="Filter by level: INFO, WARN, ERROR"),
) -> LogsResponse:
    """
    Returns recent application log entries from the in-memory ring buffer.
    Supports filtering by log level.
    """
    entries = list(_log_buffer)
    if level:
        entries = [e for e in entries if e["level"].upper() == level.upper()]

    # Most recent first
    entries = entries[-limit:][::-1]

    return LogsResponse(
        logs=[LogEntry(**e) for e in entries],
        total=len(entries),
    )
