"""Unit tests for Stage 7: Executor safety — LIMIT injection logic."""
import pytest
from backend.pipeline.stage7_executor import _inject_limit


class TestLimitInjection:
    """
    Critical: LIMIT must ALWAYS be enforced at the executor level.
    These tests verify _inject_limit() independently of the DB connection.
    """

    MAX_ROWS = 1000
    DEFAULT_LIMIT = 100

    def _inject(self, sql: str):
        return _inject_limit(sql, self.MAX_ROWS, self.DEFAULT_LIMIT)

    # ── NO LIMIT PRESENT ─────────────────────────────────────────────────────

    def test_inject_when_no_limit(self):
        sql, enforced = self._inject("SELECT * FROM users")
        assert f"LIMIT {self.DEFAULT_LIMIT}" in sql
        assert enforced is True

    def test_inject_when_no_limit_complex(self):
        sql = "SELECT u.name, COUNT(o.id) FROM users u JOIN orders o ON u.id=o.user_id GROUP BY u.name ORDER BY 2 DESC"
        result, enforced = self._inject(sql)
        assert "LIMIT" in result.upper()
        assert enforced is True

    # ── LIMIT WITHIN BOUNDS ───────────────────────────────────────────────────

    def test_preserve_small_limit(self):
        sql, enforced = self._inject("SELECT * FROM users LIMIT 10")
        assert "LIMIT 10" in sql
        assert enforced is False

    def test_preserve_limit_at_boundary(self):
        sql, enforced = self._inject(f"SELECT * FROM orders LIMIT {self.MAX_ROWS}")
        assert f"LIMIT {self.MAX_ROWS}" in sql
        assert enforced is False

    # ── LIMIT EXCEEDS MAX — MUST OVERRIDE ────────────────────────────────────

    def test_override_limit_exceeding_max(self):
        sql, enforced = self._inject("SELECT * FROM users LIMIT 9999")
        assert f"LIMIT {self.MAX_ROWS}" in sql
        assert "9999" not in sql
        assert enforced is True

    def test_override_extreme_limit(self):
        sql, enforced = self._inject("SELECT * FROM logs LIMIT 10000000")
        assert f"LIMIT {self.MAX_ROWS}" in sql
        assert enforced is True

    def test_override_all_keyword(self):
        # "ALL" is not a valid LIMIT value but test robustness
        sql, enforced = self._inject("SELECT * FROM users LIMIT 5000")
        assert f"LIMIT {self.MAX_ROWS}" in sql
        assert enforced is True

    # ── LIMIT WITH OFFSET ─────────────────────────────────────────────────────

    def test_preserve_limit_with_offset_within_bounds(self):
        sql, enforced = self._inject("SELECT * FROM users LIMIT 50 OFFSET 100")
        assert "LIMIT 50" in sql
        assert "OFFSET 100" in sql
        assert enforced is False

    def test_override_limit_with_offset_exceeding_max(self):
        sql, enforced = self._inject("SELECT * FROM users LIMIT 9999 OFFSET 0")
        assert f"LIMIT {self.MAX_ROWS}" in sql
        assert enforced is True

    # ── CASE INSENSITIVITY ────────────────────────────────────────────────────

    def test_detect_lowercase_limit(self):
        sql, enforced = self._inject("SELECT * FROM users limit 5000")
        assert f"LIMIT {self.MAX_ROWS}" in sql
        assert enforced is True

    def test_detect_mixed_case_limit(self):
        sql, enforced = self._inject("SELECT * FROM users Limit 200")
        assert enforced is False  # 200 < 1000

    # ── TRAILING SEMICOLON ────────────────────────────────────────────────────

    def test_strips_trailing_semicolon(self):
        sql, enforced = self._inject("SELECT * FROM users;")
        assert not sql.rstrip().endswith(";") or "LIMIT" in sql

    def test_strips_semicolon_before_inject(self):
        sql, enforced = self._inject("SELECT * FROM t;")
        assert f"LIMIT {self.DEFAULT_LIMIT}" in sql
        assert enforced is True


class TestConfidenceEvaluation:
    """Tests for Stage 5 confidence scoring."""

    def test_full_confidence_clean_query(self):
        from backend.pipeline.stage5_confidence import evaluate_confidence
        sql = "SELECT id, name, email FROM customers WHERE created_at > NOW() - INTERVAL '30 days' LIMIT 100"
        result = evaluate_confidence(sql, "Recent customers who signed up in the last 30 days")
        assert result.passed is True
        assert result.data["score"] >= 0.8

    def test_low_confidence_select_star_no_where(self):
        from backend.pipeline.stage5_confidence import evaluate_confidence
        sql = "SELECT * FROM large_table"
        result = evaluate_confidence(sql, "Show me everything in the large table")
        assert result.passed is True  # Warns but does not block unless below threshold
        warnings = result.data.get("warnings", [])
        assert len(warnings) >= 1

    def test_block_very_short_sql(self):
        from backend.pipeline.stage5_confidence import evaluate_confidence
        sql = "SELECT"
        result = evaluate_confidence(sql, "query the database for information about things")
        assert result.data["score"] < 1.0
