"""Structured JSON logging setup."""
import logging
import sys
from backend.config import get_settings


def setup_logging():
    cfg = get_settings()
    level = getattr(logging, cfg.log_level.upper(), logging.INFO)

    if cfg.log_format == "json":
        try:
            import structlog
            structlog.configure(
                processors=[
                    structlog.stdlib.add_log_level,
                    structlog.stdlib.add_logger_name,
                    structlog.processors.TimeStamper(fmt="iso"),
                    structlog.processors.JSONRenderer(),
                ],
                wrapper_class=structlog.stdlib.BoundLogger,
                logger_factory=structlog.stdlib.LoggerFactory(),
            )
        except ImportError:
            _setup_basic(level)
    else:
        _setup_basic(level)


def _setup_basic(level: int):
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # Silence noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
