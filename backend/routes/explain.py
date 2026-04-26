"""POST /explain — LLM explanation of a SQL statement (on-demand only)."""
import logging
from fastapi import APIRouter
from backend.models.schemas import ExplainRequest, ExplainResponse
from backend.services.gemini import GeminiProvider

log = logging.getLogger(__name__)
router = APIRouter()

EXPLAIN_SYSTEM_PROMPT = """You are a SQL educator explaining queries to business users.
Explain the SQL query in plain English:
- What data it retrieves
- Which tables are joined and why
- What filters/conditions are applied
- What aggregations or transformations are performed
- What the result set will look like

Be concise (3-5 sentences). Use non-technical language where possible.
Do NOT suggest modifications. Do NOT add SQL code. Only explain."""


@router.post("/explain", response_model=ExplainResponse, summary="Explain a SQL query in plain English")
async def explain(req: ExplainRequest) -> ExplainResponse:
    """
    On-demand SQL explanation endpoint. Separate from /query by design —
    explanation is triggered explicitly, not automatically on every query.

    Uses Gemini to produce a plain-English explanation of the SQL logic.
    """
    log.info("Explain request: session=%s, sql=%s…", req.session_id, req.sql[:60])

    gemini = GeminiProvider.get_instance()

    try:
        explanation = await gemini.generate(
            system_prompt=EXPLAIN_SYSTEM_PROMPT,
            user_prompt=f"Explain this SQL query:\n\n{req.sql}",
            max_tokens=400,
            temperature=0.2,
        )
    except Exception as e:
        log.error("Explain failed: %s", e)
        explanation = f"Explanation unavailable: {e}"

    return ExplainResponse(
        sql=req.sql,
        explanation=explanation.strip(),
        session_id=req.session_id,
    )
