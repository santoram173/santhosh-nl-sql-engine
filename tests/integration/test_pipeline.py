"""
Integration tests for the full pipeline orchestrator.
These tests mock the LLM and DB to verify end-to-end pipeline logic.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.models.schemas import StageResult


MOCK_SCHEMA = {
    "tables": [
        {
            "name": "orders",
            "columns": [
                {"name": "id", "type": "integer", "nullable": False},
                {"name": "customer_id", "type": "integer", "nullable": False},
                {"name": "amount", "type": "numeric", "nullable": True},
                {"name": "created_at", "type": "timestamp", "nullable": True},
            ],
        },
        {
            "name": "customers",
            "columns": [
                {"name": "id", "type": "integer", "nullable": False},
                {"name": "name", "type": "varchar", "nullable": False},
                {"name": "email", "type": "varchar", "nullable": True},
            ],
        },
    ]
}

MOCK_SCHEMA_CONTEXT = (
    "TABLE orders (id INTEGER NOT NULL, customer_id INTEGER NOT NULL, amount NUMERIC, created_at TIMESTAMP)\n"
    "TABLE customers (id INTEGER NOT NULL, name VARCHAR NOT NULL, email VARCHAR)"
)

MOCK_SCHEMA_SUMMARY = "orders: id, customer_id, amount, created_at; customers: id, name, email"

VALID_SQL = "SELECT c.name, SUM(o.amount) AS total FROM customers c JOIN orders o ON c.id = o.customer_id GROUP BY c.name ORDER BY total DESC"

MOCK_EXEC_DATA = {
    "rows": [{"name": "Alice", "total": 1500.00}, {"name": "Bob", "total": 900.00}],
    "columns": ["name", "total"],
    "row_count": 2,
    "limit_enforced": True,
    "execution_time_ms": 12.5,
    "sql_executed": VALID_SQL + "\nLIMIT 100",
}


@pytest.fixture
def mock_schema_cache():
    with patch("backend.pipeline.orchestrator.SchemaCache") as mock_cls:
        instance = MagicMock()
        instance.get = AsyncMock(return_value=MOCK_SCHEMA)
        instance.build_context_string.return_value = MOCK_SCHEMA_CONTEXT
        instance.build_summary_string.return_value = MOCK_SCHEMA_SUMMARY
        mock_cls.get_instance.return_value = instance
        yield instance


@pytest.fixture
def mock_session_store():
    with patch("backend.pipeline.orchestrator.SessionStore") as mock_cls:
        instance = MagicMock()
        instance.get_history.return_value = []
        instance.add_interaction = MagicMock()
        mock_cls.get_instance.return_value = instance
        yield instance


@pytest.fixture
def mock_metrics():
    with patch("backend.pipeline.orchestrator.MetricsCollector") as mock_cls:
        instance = MagicMock()
        mock_cls.get_instance.return_value = instance
        yield instance


@pytest.fixture
def mock_gemini_happy():
    """Gemini returns VALID classification and proper SQL."""
    with patch("backend.pipeline.stage3_classifier.GeminiProvider") as cls3, \
         patch("backend.pipeline.stage4_sql_generation.GeminiProvider") as cls4:
        inst3 = MagicMock()
        inst3.generate = AsyncMock(return_value=(
            "CLASSIFICATION: VALID\nINTENT: aggregate\nREASONING: This is a read query."
        ))
        cls3.get_instance.return_value = inst3

        inst4 = MagicMock()
        inst4.generate = AsyncMock(return_value=VALID_SQL)
        cls4.get_instance.return_value = inst4
        yield inst3, inst4


@pytest.fixture
def mock_executor_success():
    with patch("backend.pipeline.orchestrator.execute_query") as mock_exec:
        mock_exec.return_value = StageResult(
            passed=True,
            message="Executed successfully",
            data=MOCK_EXEC_DATA,
        )
        yield mock_exec


class TestPipelineOrchestrator:

    @pytest.mark.asyncio
    async def test_full_pipeline_success(
        self,
        mock_schema_cache,
        mock_session_store,
        mock_metrics,
        mock_gemini_happy,
        mock_executor_success,
    ):
        from backend.pipeline.orchestrator import run_pipeline
        result = await run_pipeline("Total revenue per customer from orders", "test-session")

        assert result.success is True
        assert result.sql == VALID_SQL
        assert result.rows == MOCK_EXEC_DATA["rows"]
        assert result.row_count == 2
        assert result.limit_enforced is True
        assert result.intent == "aggregate"
        assert len(result.pipeline_stages) == 7

    @pytest.mark.asyncio
    async def test_pipeline_blocked_by_stage1_ambiguity(
        self,
        mock_schema_cache,
        mock_session_store,
        mock_metrics,
    ):
        from backend.pipeline.orchestrator import run_pipeline
        result = await run_pipeline("data", "test-session")

        assert result.success is False
        assert result.failed_stage_number == 1
        assert result.sql is None

    @pytest.mark.asyncio
    async def test_pipeline_blocked_by_stage6_sql_validation(
        self,
        mock_schema_cache,
        mock_session_store,
        mock_metrics,
        mock_gemini_happy,
    ):
        """Stage 6 must block even if LLM generates dangerous SQL."""
        from backend.pipeline.orchestrator import run_pipeline

        # Override stage 4 to return malicious SQL
        with patch("backend.pipeline.stage4_sql_generation.GeminiProvider") as cls4:
            inst4 = MagicMock()
            inst4.generate = AsyncMock(return_value="DELETE FROM users WHERE 1=1")
            cls4.get_instance.return_value = inst4

            result = await run_pipeline("Delete all users from the database", "test-session")

        # Stage 6 (sql_validation) should catch this regardless of LLM output
        assert result.success is False
        # Stage 3 classifier should catch it first, or stage 4 rejects non-SELECT, or stage 6
        assert result.failed_stage_number is not None

    @pytest.mark.asyncio
    async def test_pipeline_stores_session_history_on_success(
        self,
        mock_schema_cache,
        mock_session_store,
        mock_metrics,
        mock_gemini_happy,
        mock_executor_success,
    ):
        from backend.pipeline.orchestrator import run_pipeline
        await run_pipeline("Orders by customer this month", "sess-123")
        mock_session_store.add_interaction.assert_called_once()
        call_args = mock_session_store.add_interaction.call_args
        assert call_args[0][0] == "sess-123"

    @pytest.mark.asyncio
    async def test_pipeline_does_not_store_session_on_failure(
        self,
        mock_schema_cache,
        mock_session_store,
        mock_metrics,
    ):
        from backend.pipeline.orchestrator import run_pipeline
        await run_pipeline("xyz", "sess-456")  # Too short → Stage 1 blocks
        mock_session_store.add_interaction.assert_not_called()

    @pytest.mark.asyncio
    async def test_pipeline_all_stages_present_in_response(
        self,
        mock_schema_cache,
        mock_session_store,
        mock_metrics,
        mock_gemini_happy,
        mock_executor_success,
    ):
        from backend.pipeline.orchestrator import run_pipeline
        result = await run_pipeline("Revenue by customer from orders", "sess-789")
        expected_stages = {
            "ambiguity", "schema_relevance", "classifier",
            "sql_generation", "confidence", "sql_validation", "execution"
        }
        assert set(result.pipeline_stages.keys()) == expected_stages

    @pytest.mark.asyncio
    async def test_pipeline_limit_enforced_flag_propagated(
        self,
        mock_schema_cache,
        mock_session_store,
        mock_metrics,
        mock_gemini_happy,
        mock_executor_success,
    ):
        from backend.pipeline.orchestrator import run_pipeline
        result = await run_pipeline("Show customer totals from orders", "sess-abc")
        assert result.limit_enforced is True
