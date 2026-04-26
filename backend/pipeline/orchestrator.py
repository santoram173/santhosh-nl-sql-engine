"""
Pipeline Orchestrator
=====================
Runs all 7 stages in sequence. Each stage is a hard gate.
If any stage fails, execution stops and a structured error is returned.
"""
from __future__ import annotations
import logging
import time
from typing import Any

from backend.models.schemas import QueryResponse, StageResult
from backend.pipeline.stage1_ambiguity import check_ambiguity
from backend.pipeline.stage2_schema_relevance import check_schema_relevance
from backend.pipeline.stage3_classifier import classify_intent
from backend.pipeline.stage4_sql_generation import generate_sql
from backend.pipeline.stage5_confidence import evaluate_confidence
from backend.pipeline.stage6_sql_validation import validate_sql
from backend.pipeline.stage7_executor import execute_query
from backend.services.schema_cache import SchemaCache
from backend.services.session_store import SessionStore
from backend.services.metrics import MetricsCollector

log = logging.getLogger(__name__)

STAGE_NUMBERS = {
    "ambiguity":       1,
    "schema_relevance": 2,
    "classifier":      3,
    "sql_generation":  4,
    "confidence":      5,
    "sql_validation":  6,
    "execution":       7,
}


async def run_pipeline(question: str, session_id: str) -> QueryResponse:
    """
    Execute the full 7-stage query pipeline.
    Returns a structured QueryResponse regardless of outcome.
    """
    t_start = time.perf_counter()
    metrics = MetricsCollector.get_instance()
    metrics.record_query_start()

    pipeline_stages: dict[str, StageResult] = {}
    warnings: list[str] = []

    # ── Load context ──────────────────────────────────────────────────────────
    schema_cache = SchemaCache.get_instance()
    schema = await schema_cache.get()
    schema_context = schema_cache.build_context_string(schema)
    schema_summary = schema_cache.build_summary_string(schema)

    session_store = SessionStore.get_instance()
    session_history = session_store.get_history(session_id)

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 1 — Ambiguity Check
    # ─────────────────────────────────────────────────────────────────────────
    s1 = check_ambiguity(question)
    pipeline_stages["ambiguity"] = s1
    if not s1.passed:
        metrics.record_blocked("ambiguity")
        return _error_response(question, "ambiguity", 1, s1.message, pipeline_stages)

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 2 — Schema Relevance Check
    # ─────────────────────────────────────────────────────────────────────────
    s2 = check_schema_relevance(question, schema)
    pipeline_stages["schema_relevance"] = s2
    if not s2.passed:
        metrics.record_blocked("schema_relevance")
        return _error_response(question, "Schema Relevance Check", 2, s2.message, pipeline_stages)

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 3 — LLM Classifier
    # ─────────────────────────────────────────────────────────────────────────
    s3 = await classify_intent(question, schema_summary)
    pipeline_stages["classifier"] = s3
    if not s3.passed:
        metrics.record_blocked("classifier")
        return _error_response(question, "LLM Classifier", 3, s3.message, pipeline_stages)

    intent = s3.data.get("intent", "unknown")

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 4 — SQL Generation
    # ─────────────────────────────────────────────────────────────────────────
    s4 = await generate_sql(question, schema_context, intent, session_history)
    pipeline_stages["sql_generation"] = s4
    if not s4.passed:
        metrics.record_blocked("sql_generation")
        return _error_response(question, "SQL Generation", 4, s4.message, pipeline_stages)

    generated_sql = s4.data["sql"]

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 5 — Confidence Evaluation
    # ─────────────────────────────────────────────────────────────────────────
    s5 = evaluate_confidence(generated_sql, question)
    pipeline_stages["confidence"] = s5
    warnings.extend(s5.data.get("warnings", []))
    confidence_score = s5.data.get("score", 1.0)

    if not s5.passed:
        metrics.record_blocked("confidence")
        return _error_response(question, "Confidence Evaluation", 5, s5.message, pipeline_stages)

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 6 — SQL Validation
    # ─────────────────────────────────────────────────────────────────────────
    s6 = validate_sql(generated_sql)
    pipeline_stages["sql_validation"] = s6
    if not s6.passed:
        metrics.record_blocked("sql_validation")
        log.warning("Stage 6 blocked SQL: %s…", generated_sql[:120])
        return _error_response(question, "SQL Validation", 6, s6.message, pipeline_stages)

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 7 — Execution
    # ─────────────────────────────────────────────────────────────────────────
    s7 = await execute_query(generated_sql)
    pipeline_stages["execution"] = s7

    elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)

    if not s7.passed:
        metrics.record_failed()
        return _error_response(question, "Execution", 7, s7.message, pipeline_stages)

    # ── SUCCESS ───────────────────────────────────────────────────────────────
    exec_data = s7.data
    metrics.record_success(elapsed_ms)

    # Store in session history
    session_store.add_interaction(session_id, {
        "question": question,
        "sql": generated_sql,
        "intent": intent,
        "row_count": exec_data.get("row_count", 0),
    })

    return QueryResponse(
        success=True,
        question=question,
        sql=generated_sql,
        rows=exec_data.get("rows", []),
        columns=exec_data.get("columns", []),
        row_count=exec_data.get("row_count", 0),
        limit_enforced=exec_data.get("limit_enforced", False),
        intent=intent,
        confidence=confidence_score,
        warnings=warnings,
        execution_time_ms=exec_data.get("execution_time_ms", elapsed_ms),
        pipeline_stages=pipeline_stages,
    )


def _error_response(
    question: str,
    failed_stage: str,
    stage_number: int,
    error_msg: str,
    pipeline_stages: dict[str, StageResult],
) -> QueryResponse:
    return QueryResponse(
        success=False,
        question=question,
        error=error_msg,
        failed_stage=failed_stage,
        failed_stage_number=stage_number,
        pipeline_stages=pipeline_stages,
    )
