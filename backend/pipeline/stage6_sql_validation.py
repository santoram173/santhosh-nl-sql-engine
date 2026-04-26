"""
Stage 6 — SQL Validation (Strict Safety Rules)
===============================================
HARD gate — the most critical safety layer.

This stage is INDEPENDENT of the LLM. It enforces safety rules at the
backend level regardless of what the LLM generated. The LLM is NEVER
trusted to self-enforce these rules.

Blocks:
  - Any DML: INSERT, UPDATE, DELETE
  - Any DDL: DROP, ALTER, CREATE, TRUNCATE
  - Permission changes: GRANT, REVOKE
  - System access: EXECUTE, CALL, xp_*, OPENROWSET
  - Multiple statements (;-separated)
  - Comment-based injection attempts
  - pg_* system functions that bypass security
"""
from __future__ import annotations
import re
import logging
from backend.models.schemas import StageResult

log = logging.getLogger(__name__)

# Statements that are NEVER allowed (hard block)
FORBIDDEN_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "GRANT", "REVOKE", "EXECUTE", "EXEC", "CALL",
    "MERGE", "UPSERT", "REPLACE",
    "COPY",             # PostgreSQL COPY can read/write files
    "VACUUM",           # Maintenance command
    "REINDEX",          # Maintenance
    "CLUSTER",          # Maintenance
    "ANALYZE",          # Writes statistics (pg)
    "COMMENT",          # Can modify object metadata
    "SECURITY LABEL",
    "SET ROLE",
    "SET SESSION",
    "BEGIN",            # Transaction control — executor handles this
    "COMMIT",
    "ROLLBACK",
    "SAVEPOINT",
]

# Dangerous pg_* functions
FORBIDDEN_FUNCTIONS = [
    "pg_read_file", "pg_write_file", "pg_ls_dir", "pg_stat_file",
    "pg_reload_conf", "pg_terminate_backend", "pg_cancel_backend",
    "lo_import", "lo_export",
    "dblink",
    "openquery",
]

# Dangerous patterns that might bypass keyword detection
FORBIDDEN_PATTERNS = [
    r";\s*(?:DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|TRUNCATE|GRANT|REVOKE)",  # Statement chaining
    r"--\s*(?:DROP|DELETE|UPDATE|INSERT)",                                       # Comment bypass
    r"/\*[\s\S]*?(?:DROP|DELETE|UPDATE|INSERT)[\s\S]*?\*/",                    # Block comment bypass
    r"\bINTO\s+(?:OUTFILE|DUMPFILE)\b",                                         # MySQL file write
    r"\bxp_\w+\b",                                                               # MSSQL extended procs
    r"\bSELECT\s+.*\bINTO\s+\w+",                                              # SELECT INTO (creates table)
    r"\bCREATE\s+\w+\s+AS\s+SELECT\b",                                         # CTAS
]


def _strip_string_literals(sql: str) -> str:
    """Remove string literal content to prevent false positives / false negatives."""
    # Replace 'content' with ''
    return re.sub(r"'[^']*'", "''", sql)


def validate_sql(sql: str) -> StageResult:
    """
    Stage 6: Strict safety validation of generated SQL.

    This is the LAST safety gate before execution. It must be conservative.
    """
    if not sql or not sql.strip():
        return StageResult(passed=False, message="Empty SQL — nothing to execute.")

    # Work on a cleaned version for keyword detection
    sql_clean = _strip_string_literals(sql).upper()
    sql_upper = sql.upper().strip()

    # Rule 1: Must start with SELECT or WITH
    first_token = sql_upper.split()[0] if sql_upper.split() else ""
    if first_token not in ("SELECT", "WITH"):
        return StageResult(
            passed=False,
            message=f"SQL must begin with SELECT or WITH. Got: {first_token!r}. "
                    "Only read queries are permitted.",
        )

    # Rule 2: Check for forbidden keywords using word-boundary matching
    for keyword in FORBIDDEN_KEYWORDS:
        # Use word boundary to avoid false positives (e.g. "CREATES" is not "CREATE")
        pattern = rf"\b{re.escape(keyword)}\b"
        if re.search(pattern, sql_clean, re.IGNORECASE):
            log.warning("Stage 6: BLOCKED — forbidden keyword: %s", keyword)
            return StageResult(
                passed=False,
                message=f"SQL contains forbidden keyword: {keyword!r}. "
                        "Only SELECT queries are permitted — data modification is not allowed.",
            )

    # Rule 3: Check for forbidden pg_* functions
    for fn in FORBIDDEN_FUNCTIONS:
        if fn.upper() in sql_clean:
            log.warning("Stage 6: BLOCKED — forbidden function: %s", fn)
            return StageResult(
                passed=False,
                message=f"SQL uses restricted system function: {fn!r}.",
            )

    # Rule 4: Pattern-based injection / bypass detection
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, sql_clean, re.IGNORECASE):
            log.warning("Stage 6: BLOCKED — forbidden pattern match: %s", pattern[:40])
            return StageResult(
                passed=False,
                message="SQL contains a pattern that violates safety rules. "
                        "Please rephrase your question.",
            )

    # Rule 5: Multiple statement detection (semicolon)
    # Only allow a semicolon at the very end (optional trailing semicolon)
    sql_no_trail = sql.rstrip().rstrip(";").rstrip()
    if ";" in sql_no_trail:
        return StageResult(
            passed=False,
            message="SQL contains multiple statements (semicolon detected). "
                    "Only single SELECT statements are permitted.",
        )

    # Rule 6: Validate WITH clause (CTE) — all inner queries must be SELECT
    cte_bodies = re.findall(r"\)\s*(?:AS\s*)?\(([^)]+)\)", sql, re.IGNORECASE)
    for body in cte_bodies:
        body_first = body.strip().split()[0].upper() if body.strip().split() else ""
        if body_first and body_first not in ("SELECT", "WITH", "VALUES"):
            return StageResult(
                passed=False,
                message=f"CTE body contains non-SELECT statement: {body_first!r}.",
            )

    log.debug("Stage 6 (SQL Validation): PASSED")
    return StageResult(
        passed=True,
        message="SQL passed all safety checks.",
        data={"sql_length": len(sql), "first_token": first_token},
    )
