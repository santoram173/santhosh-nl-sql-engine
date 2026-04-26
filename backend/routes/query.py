"""POST /query — run the full 7-stage pipeline."""
import logging
from fastapi import APIRouter, HTTPException
from backend.models.schemas import QueryRequest, QueryResponse
from backend.pipeline.orchestrator import run_pipeline
from backend.services.metrics import MetricsCollector

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/query", response_model=QueryResponse, summary="Execute NL query through 7-stage pipeline")
async def query(req: QueryRequest) -> QueryResponse:
    """
    Submit a natural language question. It will pass through all 7 pipeline stages:

    1. **Ambiguity Check** — rule-based vagueness detection
    2. **Schema Relevance** — fuzzy match against DB schema
    3. **LLM Classifier** — VALID/INVALID intent classification
    4. **SQL Generation** — LLM generates SQL with schema context
    5. **Confidence Eval** — rule-based quality warnings
    6. **SQL Validation** — strict safety gate (blocks DDL/DML)
    7. **Execution** — asyncpg read-only with enforced LIMIT

    Any stage failure returns a structured error with the blocking stage identified.
    """
    log.info("Query received: session=%s, q=%s", req.session_id, req.question[:80])
    result = await run_pipeline(req.question, req.session_id)
    return result
