"""GET /schema — return cached DB schema."""
import logging
from fastapi import APIRouter, Query
from backend.models.schemas import SchemaResponse, SchemaTable, SchemaColumn
from backend.services.schema_cache import SchemaCache

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/schema", response_model=SchemaResponse, summary="Get database schema")
async def get_schema(refresh: bool = Query(default=False, description="Force schema refresh")) -> SchemaResponse:
    """
    Returns the cached database schema (tables, columns, types).

    Uses MD5 fingerprinting — only re-queries the DB when the schema changes.
    Pass `?refresh=true` to force an immediate refresh.
    """
    cache = SchemaCache.get_instance()

    if refresh:
        log.info("Forced schema refresh requested")
        await cache.refresh()

    raw = await cache.get()

    tables = [
        SchemaTable(
            name=t["name"],
            columns=[
                SchemaColumn(
                    name=c["name"],
                    type=c["type"],
                    nullable=c.get("nullable", True),
                )
                for c in t.get("columns", [])
            ],
            row_count=t.get("row_count"),
        )
        for t in raw.get("tables", [])
    ]

    return SchemaResponse(
        tables=tables,
        fingerprint=cache.fingerprint,
        cached_at=cache.cached_at_str,
    )
