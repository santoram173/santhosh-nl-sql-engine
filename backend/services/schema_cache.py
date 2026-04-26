"""
Schema Cache
============
Caches database schema with TTL and MD5 fingerprint for change detection.
Auto-refreshes only when fingerprint changes.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import time
from typing import Optional

from backend.config import get_settings

log = logging.getLogger(__name__)

INTROSPECT_SQL = """
SELECT
    t.table_name,
    c.column_name,
    c.data_type,
    c.is_nullable,
    c.column_default,
    c.character_maximum_length,
    c.numeric_precision
FROM information_schema.tables t
JOIN information_schema.columns c
  ON t.table_name = c.table_name
  AND t.table_schema = c.table_schema
WHERE t.table_schema = 'public'
  AND t.table_type = 'BASE TABLE'
ORDER BY t.table_name, c.ordinal_position;
"""

ROW_COUNT_SQL = """
SELECT relname AS table_name, n_live_tup AS row_count
FROM pg_stat_user_tables
ORDER BY relname;
"""


class SchemaCache:
    _instance: Optional["SchemaCache"] = None

    def __init__(self):
        cfg = get_settings()
        self._ttl = cfg.schema_cache_ttl
        self._schema: dict = {}
        self._fingerprint: str = ""
        self._cached_at: float = 0
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> "SchemaCache":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def get(self) -> dict:
        """Return cached schema, refreshing if TTL expired."""
        now = time.time()
        if not self._schema or (now - self._cached_at) > self._ttl:
            await self.refresh()
        return self._schema

    async def refresh(self) -> None:
        """Fetch schema from DB; skip update if fingerprint unchanged."""
        async with self._lock:
            try:
                from backend.database.pool import get_pool
                pool = get_pool()
                async with pool.acquire() as conn:
                    rows = await conn.fetch(INTROSPECT_SQL)
                    count_rows = await conn.fetch(ROW_COUNT_SQL)

                # Build row count map
                row_counts = {r["table_name"]: r["row_count"] for r in count_rows}

                # Build schema dict
                tables: dict[str, dict] = {}
                for row in rows:
                    tname = row["table_name"]
                    if tname not in tables:
                        tables[tname] = {
                            "name": tname,
                            "columns": [],
                            "row_count": row_counts.get(tname),
                        }
                    tables[tname]["columns"].append({
                        "name": row["column_name"],
                        "type": row["data_type"],
                        "nullable": row["is_nullable"] == "YES",
                    })

                schema = {"tables": list(tables.values())}
                new_fp = hashlib.md5(json.dumps(schema, sort_keys=True).encode()).hexdigest()

                if new_fp != self._fingerprint:
                    log.info(
                        "Schema refreshed: %d tables, fingerprint=%s",
                        len(tables), new_fp[:8],
                    )
                    self._schema = schema
                    self._fingerprint = new_fp
                else:
                    log.debug("Schema unchanged (fingerprint=%s)", new_fp[:8])

                self._cached_at = time.time()

            except Exception as e:
                log.error("Schema cache refresh failed: %s", e)
                if not self._schema:
                    self._schema = {"tables": []}

    def build_context_string(self, schema: dict) -> str:
        """Build detailed schema context for SQL generation prompt."""
        lines = []
        for table in schema.get("tables", []):
            col_defs = ", ".join(
                f"{c['name']} {c['type'].upper()}"
                + ("" if c.get("nullable") else " NOT NULL")
                for c in table["columns"]
            )
            rc = f" -- ~{table['row_count']:,} rows" if table.get("row_count") else ""
            lines.append(f"TABLE {table['name']} ({col_defs}){rc}")
        return "\n".join(lines)

    def build_summary_string(self, schema: dict) -> str:
        """Build brief schema summary for classifier prompt."""
        summaries = []
        for table in schema.get("tables", []):
            col_names = [c["name"] for c in table["columns"][:6]]
            more = len(table["columns"]) - 6
            suffix = f" +{more} more" if more > 0 else ""
            summaries.append(f"{table['name']}: {', '.join(col_names)}{suffix}")
        return "; ".join(summaries)

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    @property
    def cached_at_str(self) -> str:
        if not self._cached_at:
            return "never"
        import datetime
        return datetime.datetime.fromtimestamp(self._cached_at).isoformat()
