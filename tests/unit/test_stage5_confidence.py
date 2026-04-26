"""Unit tests for Stage 5: Confidence Evaluation."""
import pytest
from backend.pipeline.stage5_confidence import evaluate_confidence


class TestConfidenceEvaluation:

    def test_high_confidence_clean_query(self):
        sql = (
            "SELECT c.name, SUM(o.amount) AS total "
            "FROM customers c JOIN orders o ON c.id = o.customer_id "
            "WHERE o.created_at >= NOW() - INTERVAL '30 days' "
            "GROUP BY c.name ORDER BY total DESC LIMIT 10"
        )
        result = evaluate_confidence(sql, "Top customers by revenue in the last 30 days")
        assert result.passed is True
        # SELECT has named columns, WHERE clause present, no SELECT *, proper JOIN
        assert result.data["score"] >= 0.7

    def test_warn_select_star(self):
        sql = "SELECT * FROM orders WHERE status = 'pending'"
        result = evaluate_confidence(sql, "Show pending orders")
        assert result.passed is True
        warnings = result.data.get("warnings", [])
        assert any("SELECT *" in w or "column" in w.lower() for w in warnings)

    def test_warn_no_where_clause(self):
        sql = "SELECT id, name FROM customers"
        result = evaluate_confidence(sql, "Show all customers")
        assert result.passed is True
        warnings = result.data.get("warnings", [])
        assert any("WHERE" in w or "scan" in w.lower() for w in warnings)

    def test_warn_missing_group_by_for_monthly(self):
        sql = "SELECT amount FROM orders WHERE created_at > '2025-01-01'"
        result = evaluate_confidence(sql, "Show revenue by month")
        warnings = result.data.get("warnings", [])
        assert any("GROUP BY" in w for w in warnings)

    def test_block_very_short_sql(self):
        sql = "SELECT 1"
        result = evaluate_confidence(sql, "Show detailed customer analytics breakdown by region")
        assert result.data["score"] < 0.9

    def test_score_is_between_0_and_1(self):
        sql = "SELECT * FROM t"
        result = evaluate_confidence(sql, "get all t")
        score = result.data["score"]
        assert 0.0 <= score <= 1.0

    def test_pass_returns_score_in_data(self):
        sql = "SELECT id, name FROM customers WHERE country = 'US' LIMIT 50"
        result = evaluate_confidence(sql, "US customers list")
        assert "score" in result.data
        assert "warnings" in result.data

    def test_multiple_warnings_reduce_score(self):
        sql = "SELECT *"
        result = evaluate_confidence(sql, "show everything grouped by month")
        score = result.data["score"]
        warnings = result.data["warnings"]
        assert score < 1.0
        assert len(warnings) >= 1
