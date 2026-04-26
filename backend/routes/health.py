"""GET /health — liveness and readiness check."""
import asyncio
import logging
from fastapi import APIRouter
from backend.database.pool import get_pool
from backend.services.schema_cache import SchemaCache
from backend.services.gemini import GeminiProvider

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", summary="Health check")
async def health() -> dict:
    """
    Returns the health status of all engine components:
    - API server (always healthy if this responds)
    - Database connectivity
    - Schema cache status
    - LLM provider configuration
    """
    checks: dict[str, dict] = {}

    # Database check
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await asyncio.wait_for(conn.fetchval("SELECT 1"), timeout=3.0)
        checks["database"] = {"status": "healthy", "message": "Connection OK"}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "message": str(e)}

    # Schema cache check
    cache = SchemaCache.get_instance()
    schema = cache._schema
    checks["schema_cache"] = {
        "status": "healthy" if schema.get("tables") else "empty",
        "tables": len(schema.get("tables", [])),
        "fingerprint": cache.fingerprint[:8] if cache.fingerprint else None,
        "cached_at": cache.cached_at_str,
    }

    # LLM provider check
    gemini = GeminiProvider.get_instance()
    checks["llm"] = {
        "status": "configured" if gemini._api_key else "not_configured",
        "model": gemini._model,
        "total_calls": gemini.stats["total_calls"],
    }

    overall = (
        "healthy"
        if checks["database"]["status"] == "healthy"
        else "degraded"
    )

    return {
        "status": overall,
        "version": "1.0.0",
        "components": checks,
    }
