"""
Stage 1 — Ambiguity Check (Rule-Based)
======================================
Hard gate: reject queries that are too vague, too short, or structurally
ambiguous to produce a deterministic SQL result.
"""
from __future__ import annotations
import re
import logging
from backend.models.schemas import StageResult
from backend.config import get_settings

log = logging.getLogger(__name__)

# Phrases that indicate ambiguity without further context
AMBIGUOUS_PATTERNS = [
    r"^(show|get|give|find|list)\s+(me\s+)?(something|stuff|things|data|info|information|everything|all)[\s.!?]*$",
    r"^(show|get|give|find|list)\s+(me\s+)?all\s+(the\s+)?(data|info|information|records|rows|stuff)[\s.!?]*$",
    r"^(what|which|how|who)\??[\s.!?]*$",
    r"^(select|query|run|execute)[\s.!?]*$",
]

# Keywords that require temporal context but none is provided
TEMPORAL_WITHOUT_CONTEXT = [
    "yesterday", "last week", "last month", "this year",
    "recently", "latest", "today",
]

# Minimum meaningful word count
MIN_WORDS = 3

# Maximum characters
MAX_CHARS = 500


def check_ambiguity(question: str) -> StageResult:
    """
    Stage 1: Detect questions that are too ambiguous to generate reliable SQL.

    Returns StageResult(passed=True) if the query is clear enough to proceed.
    Returns StageResult(passed=False) with a user-friendly message if rejected.
    """
    cfg = get_settings()
    q = question.strip()

    # Rule 1: Minimum length
    words = [w for w in q.split() if w.strip()]
    if len(words) < cfg.ambiguity_min_words:
        return StageResult(
            passed=False,
            message=f"Query is too short ({len(words)} words). Please be more specific. "
                    f"Example: 'Show me total revenue by product category for last month.'",
        )

    # Rule 2: Maximum length
    if len(q) > MAX_CHARS:
        return StageResult(
            passed=False,
            message=f"Query exceeds maximum length ({MAX_CHARS} characters). Please shorten your question.",
        )

    # Rule 3: Pattern-based ambiguity
    for pattern in AMBIGUOUS_PATTERNS:
        if re.match(pattern, q, re.IGNORECASE):
            return StageResult(
                passed=False,
                message="Query is too vague. Please specify what data you want, which table or entity, "
                        "and any filters or grouping. Example: 'Top 10 customers by total orders this month.'",
            )

    # Rule 4: No meaningful content (only stop words / punctuation)
    meaningful = re.sub(r"\b(the|a|an|is|are|was|were|do|does|did|be|been|being|of|in|on|at|to|for|with|by|from|or|and|but|not|this|that|these|those|it|its|i|me|my|we|our|you|your|he|she|they|their)\b", "", q, flags=re.IGNORECASE)
    meaningful = re.sub(r"[^a-zA-Z0-9]", "", meaningful)
    if len(meaningful) < 5:
        return StageResult(
            passed=False,
            message="Query contains no meaningful content after removing common words. "
                    "Please specify tables, metrics, or entities you want to query.",
        )

    # Rule 5: Injection probe patterns
    injection_patterns = [
        r";\s*(drop|delete|update|insert|alter|create|truncate|grant|revoke)",
        r"--\s*(drop|delete|update|insert)",
        r"/\*.*?\*/",
        r"xp_\w+",
        r"exec\s*\(",
    ]
    for pat in injection_patterns:
        if re.search(pat, q, re.IGNORECASE):
            return StageResult(
                passed=False,
                message="Query contains patterns that look like SQL injection. "
                        "Please ask your question in plain English.",
            )

    log.debug("Stage 1 (Ambiguity): PASSED — %d words, %d chars", len(words), len(q))
    return StageResult(
        passed=True,
        message="Query is clear and specific.",
        data={"word_count": len(words), "char_count": len(q)},
    )
