"""
Stage 5 — Confidence Evaluation (Rule-Based Warnings)
======================================================
Soft gate: analyse the generated SQL for quality signals.
Issues warnings for low-confidence queries but does NOT block unless
confidence is below the absolute minimum threshold.
"""
from __future__ import annotations
import re
import logging
from backend.models.schemas import StageResult
from backend.config import get_settings

log = logging.getLogger(__name__)


def _count_tables(sql: str) -> int:
    """Count approximate number of table references."""
    from_parts = re.findall(r"\bFROM\b|\bJOIN\b", sql, re.IGNORECASE)
    return len(from_parts)


def _has_cartesian_risk(sql: str) -> bool:
    """Detect potential cartesian join (JOIN without ON)."""
    joins = re.findall(r"\bJOIN\b\s+\w+\s+(?!\s*ON\b)", sql, re.IGNORECASE)
    return len(joins) > 0


def _has_wildcard_select(sql: str) -> bool:
    """Detect SELECT * which may return unexpected columns."""
    return bool(re.search(r"\bSELECT\s+\*", sql, re.IGNORECASE))


def _has_no_where(sql: str) -> bool:
    """Detect full-table scan risk (no WHERE clause)."""
    return not bool(re.search(r"\bWHERE\b", sql, re.IGNORECASE))


def _has_subquery_complexity(sql: str) -> bool:
    """Detect deeply nested subqueries."""
    depth = 0
    max_depth = 0
    for c in sql:
        if c == "(":
            depth += 1
            max_depth = max(max_depth, depth)
        elif c == ")":
            depth -= 1
    return max_depth >= 4


def _uses_non_sargable_functions(sql: str) -> bool:
    """Detect functions on indexed columns that prevent index usage."""
    patterns = [
        r"\bWHERE\b.*\b(YEAR|MONTH|DAY|LOWER|UPPER|TRIM|CAST)\s*\(",
    ]
    return any(re.search(p, sql, re.IGNORECASE) for p in patterns)


def evaluate_confidence(sql: str, question: str) -> StageResult:
    """
    Stage 5: Rule-based confidence scoring with actionable warnings.
    Score 0.0–1.0. Warnings collected but only very low scores are blocked.
    """
    cfg = get_settings()
    warnings = []
    score = 1.0

    # Signal: SELECT * (ambiguous result shape)
    if _has_wildcard_select(sql):
        warnings.append("SELECT * returns all columns — consider specifying column names for clearer results.")
        score -= 0.1

    # Signal: No WHERE clause on likely large table
    if _has_no_where(sql) and _count_tables(sql) == 1:
        warnings.append("No WHERE clause detected — query may scan the entire table. Results will be limited by the backend.")
        score -= 0.15

    # Signal: Cartesian join risk
    if _has_cartesian_risk(sql):
        warnings.append("Possible JOIN without ON condition detected — verify the query produces expected results.")
        score -= 0.3

    # Signal: Deep subquery nesting
    if _has_subquery_complexity(sql):
        warnings.append("Complex nested subquery detected — query may be slow on large datasets.")
        score -= 0.1

    # Signal: Non-sargable predicates
    if _uses_non_sargable_functions(sql):
        warnings.append("Function on WHERE column may prevent index usage, causing full table scan.")
        score -= 0.1

    # Signal: Very short SQL relative to question complexity
    if len(sql) < 30:
        warnings.append("Generated SQL is very short — it may not fully represent the intended query.")
        score -= 0.2

    # Signal: Question asked for something the SQL seems to ignore
    question_lower = question.lower()
    if any(w in question_lower for w in ["by month", "monthly", "by week", "weekly"]):
        if not re.search(r"\bGROUP\s+BY\b", sql, re.IGNORECASE):
            warnings.append("Question mentions time grouping but SQL lacks GROUP BY.")
            score -= 0.15

    score = max(0.0, round(score, 2))

    log.debug("Stage 5 (Confidence): score=%.2f, warnings=%d", score, len(warnings))

    # Hard block for extremely low confidence
    if score < cfg.confidence_block_threshold:
        return StageResult(
            passed=False,
            message=f"Confidence score ({score:.0%}) is too low to safely execute this query. "
                    "Please rephrase your question more specifically.",
            data={"score": score, "warnings": warnings},
        )

    return StageResult(
        passed=True,
        message=f"Confidence: {score:.0%}" + (f" ({len(warnings)} warning(s))" if warnings else ""),
        data={"score": score, "warnings": warnings},
    )
