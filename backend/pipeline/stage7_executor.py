"""
Stage 7 — Query Executor (asyncpg, Read-Only, LIMIT Enforced)
=============================================================
CRITICAL design rules:
  1. LIMIT is ALWAYS injected by the executor — NEVER trusted from LLM output.
  2. All queries run inside read-only transactions (SET TRANSACTION READ ONLY).
  3. Connection pool with configurable timeout.
  4. Results are serialised to JSON-safe dicts.
"""
from __future__ import annotations
import logging
import re
import time
from typing import Any

import asyncpg

from backend.models.schemas import StageResult
from backend.database.pool import get_pool
from backend.config import get_settings

log = logging.getLogger(__name__)


def _inject_limit(sql: str, max_rows: int, default_limit: int) -> tuple[str, bool]:
    """
    Ensure a LIMIT clause exists and does not exceed max_rows.
    Returns (modified_sql, limit_was_enforced).

    Design:
    - If SQL has no LIMIT: inject LIMIT default_limit
    - If SQL has LIMIT N where N > max_rows: replace with LIMIT max_rows
    - If SQL has LIMIT N where N <= max_rows: leave as-is
    """
    sql = sql.rstrip().rstrip(";")

    # Detect existing LIMIT clause
    limit_pattern = re.compile(r"\bLIMIT\s+(\d+)(?:\s+OFFSET\s+(\d+))?", re.IGNORECASE)
    match = limit_pattern.search(sql)

    if match:
        existing_limit = int(match.group(1))
        if existing_limit > max_rows:
            # Replace with max_rows
            offset_clause = f" OFFSET {match.group(2)}" if match.group(2) else ""
            sql = limit_pattern.sub(f"LIMIT {max_rows}{offset_clause}", sql)
            return sql, True
        return sql, False
    else:
        # No LIMIT — inject default
        return sql + f"\nLIMIT {default_limit}", True


def _serialise_row(row: asyncpg.Record) -> dict[str, Any]:
    """Convert asyncpg Record to JSON-serialisable dict."""
    result = {}
    for key in row.keys():
        val = row[key]
        # Handle non-JSON-serialisable types
        if hasattr(val, "isoformat"):     # date / datetime / time
            result[key] = val.isoformat()
        elif hasattr(val, "__float__"):   # Decimal
            result[key] = float(val)
        elif isinstance(val, (bytes, bytearray, memoryview)):
            result[key] = val.hex()
        else:
            result[key] = val
    return result


async def execute_query(sql: str) -> StageResult:
    """
    Stage 7: Execute validated SQL in a read-only transaction.

    LIMIT is injected here — this is the definitive enforcement point.
    """
    cfg = get_settings()

    # Inject LIMIT (non-negotiable)
    safe_sql, limit_enforced = _inject_limit(sql, cfg.max_result_rows, cfg.default_limit)

    pool = get_pool()
    t_start = time.perf_counter()

    try:
        async with pool.acquire() as conn:
            # Enforce read-only at the transaction level — second line of defence
            async with conn.transaction():
                await conn.execute("SET TRANSACTION READ ONLY")
                # Set statement timeout
                await conn.execute(f"SET statement_timeout = '{cfg.db_command_timeout * 1000}'")

                records = await conn.fetch(safe_sql)

        elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)

        if not records:
            return StageResult(
                passed=True,
                message="Query executed successfully — 0 rows returned.",
                data={
                    "rows": [],
                    "columns": [],
                    "row_count": 0,
                    "limit_enforced": limit_enforced,
                    "execution_time_ms": elapsed_ms,
                    "sql_executed": safe_sql,
                },
            )

        columns = list(records[0].keys())
        rows = [_serialise_row(r) for r in records]

        log.info(
            "Stage 7 (Executor): %d rows, %.1fms, limit_enforced=%s",
            len(rows), elapsed_ms, limit_enforced,
        )

        return StageResult(
            passed=True,
            message=f"Executed successfully — {len(rows)} row(s) in {elapsed_ms}ms.",
            data={
                "rows": rows,
                "columns": columns,
                "row_count": len(rows),
                "limit_enforced": limit_enforced,
                "execution_time_ms": elapsed_ms,
                "sql_executed": safe_sql,
            },
        )

    except asyncpg.exceptions.QueryCanceledError:
        return StageResult(
            passed=False,
            message=f"Query exceeded the {cfg.db_command_timeout}s timeout. "
                    "Please add more specific filters to reduce the data scanned.",
        )
    except asyncpg.exceptions.PostgresError as e:
        log.error("Stage 7: PostgreSQL error: %s", e)
        return StageResult(
            passed=False,
            message=f"Database error: {e.args[0] if e.args else str(e)}. "
                    "The generated SQL may reference non-existent tables or columns.",
        )
    except Exception as e:
        log.exception("Stage 7: Unexpected error during execution")
        return StageResult(
            passed=False,
            message=f"Execution failed: {e}",
        )
