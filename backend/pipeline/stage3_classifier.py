"""
Stage 3 — LLM Intent Classifier
================================
Hard gate: ask the LLM to classify the query as VALID or INVALID.
If INVALID, return immediately with the LLM's reasoning.

The LLM is used ONLY for classification here — not for SQL generation.
This keeps the classifier fast and cheap (short prompt, fast response).
"""
from __future__ import annotations
import logging
from backend.models.schemas import StageResult
from backend.services.gemini import GeminiProvider

log = logging.getLogger(__name__)

CLASSIFIER_SYSTEM_PROMPT = """You are a strict SQL query intent classifier for a read-only business intelligence system.

Classify the user's question as VALID or INVALID.

VALID: The question asks for data retrieval (SELECT) and can be answered with SQL.
       Examples: counts, aggregations, filters, rankings, time-series, joins.

INVALID: The question:
- Asks to modify data (INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE)
- Is asking about the system itself, not the data
- Is completely unrelated to data querying
- Cannot possibly be answered with a SELECT query
- Contains harmful intent

Respond with EXACTLY this format (no other text):
CLASSIFICATION: VALID|INVALID
INTENT: <one of: aggregate, filter, ranking, time_series, lookup, join, count>
REASONING: <one sentence explaining your decision>"""


async def classify_intent(question: str, schema_summary: str) -> StageResult:
    """
    Stage 3: LLM classifies whether the question is a valid read query.
    """
    gemini = GeminiProvider.get_instance()

    prompt = (
        f"Database schema summary:\n{schema_summary}\n\n"
        f"User question: {question}\n\n"
        "Classify this question."
    )

    try:
        response = await gemini.generate(
            system_prompt=CLASSIFIER_SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=150,
            temperature=0.0,  # Deterministic classification
        )
    except Exception as e:
        log.warning("Stage 3: LLM classifier error: %s — defaulting to VALID", e)
        # If the classifier fails, we allow through (fail open for classifier only)
        # The SQL validator (Stage 6) is the actual safety gate
        return StageResult(
            passed=True,
            message="Classifier unavailable — proceeding with caution.",
            data={"classifier_available": False},
        )

    # Parse structured response
    lines = {
        line.split(":", 1)[0].strip(): line.split(":", 1)[1].strip()
        for line in response.strip().splitlines()
        if ":" in line
    }

    classification = lines.get("CLASSIFICATION", "").upper()
    intent = lines.get("INTENT", "unknown").lower()
    reasoning = lines.get("REASONING", "")

    if classification == "INVALID":
        log.info("Stage 3 (Classifier): BLOCKED — Intent=%s: %s", intent, reasoning)
        return StageResult(
            passed=False,
            message=f"Query classified as non-queryable: {reasoning}",
            data={"classification": "INVALID", "intent": intent, "reasoning": reasoning},
        )

    log.debug("Stage 3 (Classifier): PASSED — Intent=%s", intent)
    return StageResult(
        passed=True,
        message=f"Query classified as VALID ({intent})",
        data={"classification": "VALID", "intent": intent, "reasoning": reasoning},
    )
