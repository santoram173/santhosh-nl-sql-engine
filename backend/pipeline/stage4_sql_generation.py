"""
Stage 4 — SQL Generation (LLM with Schema Context)
===================================================
The LLM generates a raw SQL string. It is NOT trusted to enforce:
  - LIMIT clauses
  - Read-only constraints
  - Safety rules

All of those are enforced by Stage 6 (validation) and Stage 7 (executor).
"""
from __future__ import annotations
import logging
import re
from backend.models.schemas import StageResult
from backend.services.gemini import GeminiProvider

log = logging.getLogger(__name__)

SQL_GENERATION_SYSTEM_PROMPT = """You are an expert PostgreSQL query writer for a read-only business intelligence system.

Rules:
1. Generate ONLY valid PostgreSQL SELECT statements.
2. Do NOT include LIMIT — the backend enforces LIMIT automatically.
3. Do NOT use subqueries that modify data.
4. Use table and column names EXACTLY as they appear in the schema.
5. Add appropriate WHERE clauses to filter data as requested.
6. Use CTEs (WITH clauses) for complex queries.
7. Add aliases for aggregated columns to make results readable.
8. If a question mentions "last N days/months", use NOW() - INTERVAL.
9. Always qualify ambiguous column names with table aliases.
10. Return ONLY the SQL query — no explanation, no markdown, no backticks."""

SQL_GENERATION_SYSTEM_PROMPT += "\n\nCRITICAL: Output ONLY the raw SQL. No ```sql blocks. No explanation. Just SQL."


def _extract_sql(raw: str) -> str:
    """Strip markdown fences and extract raw SQL from LLM output."""
    # Remove ```sql ... ``` or ``` ... ```
    raw = re.sub(r"```(?:sql)?", "", raw, flags=re.IGNORECASE)
    raw = raw.replace("```", "")
    # Remove leading/trailing whitespace
    raw = raw.strip()
    # Remove any leading "SQL:" or "Query:" labels
    raw = re.sub(r"^(?:sql|query|answer)\s*:\s*", "", raw, flags=re.IGNORECASE)
    return raw.strip()


async def generate_sql(
    question: str,
    schema_context: str,
    intent: str,
    session_history: list[dict],
) -> StageResult:
    """
    Stage 4: Generate SQL from natural language using schema context.
    """
    gemini = GeminiProvider.get_instance()

    # Build conversation context from session history
    history_ctx = ""
    if session_history:
        recent = session_history[-3:]  # Last 3 interactions for context
        history_ctx = "\n\nPrevious queries in this session (for context only):\n"
        for h in recent:
            if h.get("sql"):
                history_ctx += f"- Q: {h['question']}\n  SQL: {h['sql'][:100]}…\n"

    prompt = (
        f"Database Schema:\n{schema_context}\n"
        f"{history_ctx}\n"
        f"Query intent: {intent}\n\n"
        f"User question: {question}\n\n"
        "Generate the PostgreSQL SELECT query:"
    )

    try:
        raw_sql = await gemini.generate(
            system_prompt=SQL_GENERATION_SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=800,
            temperature=0.05,
        )
    except Exception as e:
        log.error("Stage 4: SQL generation failed: %s", e)
        return StageResult(
            passed=False,
            message=f"SQL generation failed: {e}. Please try rephrasing your question.",
        )

    sql = _extract_sql(raw_sql)

    if not sql:
        return StageResult(
            passed=False,
            message="LLM returned empty SQL. Please try rephrasing your question.",
        )

    # Basic sanity: must start with SELECT or WITH
    first_token = sql.strip().split()[0].upper()
    if first_token not in ("SELECT", "WITH"):
        log.warning("Stage 4: LLM generated non-SELECT SQL: %s…", sql[:60])
        return StageResult(
            passed=False,
            message=f"Generated SQL does not start with SELECT or WITH. Got: {first_token}. "
                    "Only read queries are permitted.",
        )

    log.debug("Stage 4 (SQL Gen): PASSED — %d chars", len(sql))
    return StageResult(
        passed=True,
        message="SQL generated successfully.",
        data={"sql": sql, "raw_length": len(sql)},
    )
