"""asyncpg connection pool — read-only transactions enforced here."""
import asyncpg
import logging
from backend.config import get_settings

log = logging.getLogger(__name__)
_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    global _pool
    cfg = get_settings()
    log.info("Initialising asyncpg pool: min=%d max=%d", cfg.db_min_pool, cfg.db_max_pool)
    _pool = await asyncpg.create_pool(
        cfg.database_url,
        min_size=cfg.db_min_pool,
        max_size=cfg.db_max_pool,
        command_timeout=cfg.db_command_timeout,
        server_settings={"application_name": "santhosh-nl-sql"},
    )
    log.info("Database pool ready")


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        log.info("Database pool closed")


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialised. Call init_pool() first.")
    return _pool
