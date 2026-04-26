"""
Stage 2 — Schema Relevance Check (Fuzzy Matching)
==================================================
Hard gate: verify that the query mentions entities that can be resolved
to real tables or columns in the database schema.
Uses token overlap + edit-distance fuzzy matching.
"""
from __future__ import annotations
import re
import logging
from difflib import SequenceMatcher
from typing import List

from backend.models.schemas import StageResult
from backend.config import get_settings

log = logging.getLogger(__name__)

# Stop words that should not be matched against schema names
STOP_WORDS = {
    "show", "me", "get", "find", "list", "give", "what", "which", "how",
    "many", "much", "the", "a", "an", "all", "of", "in", "on", "at", "to",
    "for", "with", "by", "from", "or", "and", "but", "not", "is", "are",
    "was", "were", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "top", "first", "last", "total",
    "average", "avg", "count", "sum", "max", "min", "per", "each", "where",
    "when", "who", "whose", "that", "this", "these", "those", "their", "its",
    "data", "result", "results", "query", "select", "between", "during",
    "across", "over", "under", "about", "than", "more", "less", "group",
    "order", "sort", "filter", "limit", "offset", "number", "amount", "value",
}


def _tokenise(text: str) -> List[str]:
    """Extract meaningful tokens from text."""
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", text.lower())
    return [t for t in tokens if t not in STOP_WORDS and len(t) >= 3]


def _fuzzy_score(a: str, b: str) -> float:
    """Compute similarity ratio between two strings."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _schema_tokens(schema: dict) -> List[str]:
    """Extract all table and column names from schema dict."""
    tokens = []
    for table in schema.get("tables", []):
        tokens.append(table["name"].lower())
        for col in table.get("columns", []):
            tokens.append(col["name"].lower())
            # Also add individual parts of snake_case names
            tokens.extend(col["name"].lower().split("_"))
    return list(set(tokens))


def check_schema_relevance(question: str, schema: dict) -> StageResult:
    """
    Stage 2: Fuzzy-match query tokens against schema tables/columns.

    Passes if at least one query token matches a schema token above threshold
    AND the best match score meets a minimum quality bar.
    """
    cfg = get_settings()
    # Use a higher effective threshold to avoid noise matches like
    # "weather" → "created" (0.57) which are coincidental character overlaps.
    threshold = max(cfg.fuzzy_match_threshold, 0.65)

    if not schema or not schema.get("tables"):
        # No schema loaded — allow through and let the LLM handle it
        log.warning("Stage 2: No schema available, passing through")
        return StageResult(
            passed=True,
            message="No schema available for relevance check — proceeding.",
            data={"schema_available": False},
        )

    query_tokens = _tokenise(question)
    if not query_tokens:
        return StageResult(
            passed=False,
            message="Could not extract meaningful entities from the query. "
                    "Please mention specific tables, columns, or business entities.",
        )

    schema_tokens = _schema_tokens(schema)
    best_matches = []

    for qt in query_tokens:
        for st in schema_tokens:
            score = _fuzzy_score(qt, st)
            if score >= threshold:
                best_matches.append({"query_token": qt, "schema_token": st, "score": round(score, 3)})

    best_matches.sort(key=lambda x: x["score"], reverse=True)
    unique_matches = list({m["schema_token"]: m for m in best_matches}.values())

    if not best_matches:
        table_names = [t["name"] for t in schema.get("tables", [])]
        return StageResult(
            passed=False,
            message=(
                f"Your query doesn't seem to reference any known tables or columns. "
                f"Available tables: {', '.join(table_names)}. "
                f"Please rephrase using these entity names."
            ),
        )

    log.debug(
        "Stage 2 (Schema Relevance): PASSED — %d matches, best: %s → %s (%.2f)",
        len(best_matches),
        best_matches[0]["query_token"],
        best_matches[0]["schema_token"],
        best_matches[0]["score"],
    )
    return StageResult(
        passed=True,
        message=f"Found {len(unique_matches)} schema match(es).",
        data={"top_matches": list(best_matches)[:5]},
    )
