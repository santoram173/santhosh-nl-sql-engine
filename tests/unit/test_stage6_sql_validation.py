"""Unit tests for Stage 6: SQL Validation — the critical safety gate."""
import pytest
from backend.pipeline.stage6_sql_validation import validate_sql


class TestSQLValidation:

    # ── SHOULD PASS ──────────────────────────────────────────────────────────

    def test_pass_simple_select(self):
        result = validate_sql("SELECT id, name FROM users LIMIT 10")
        assert result.passed is True

    def test_pass_select_with_join(self):
        sql = """
        SELECT u.name, COUNT(o.id) AS order_count
        FROM users u
        JOIN orders o ON u.id = o.user_id
        GROUP BY u.name
        ORDER BY order_count DESC
        LIMIT 20
        """
        result = validate_sql(sql)
        assert result.passed is True

    def test_pass_select_with_cte(self):
        sql = """
        WITH monthly AS (
            SELECT DATE_TRUNC('month', created_at) AS month, SUM(amount) AS revenue
            FROM orders
            GROUP BY 1
        )
        SELECT * FROM monthly ORDER BY month DESC
        """
        result = validate_sql(sql)
        assert result.passed is True

    def test_pass_select_with_subquery(self):
        sql = "SELECT * FROM users WHERE id IN (SELECT user_id FROM orders WHERE total > 100)"
        result = validate_sql(sql)
        assert result.passed is True

    def test_pass_select_with_trailing_semicolon(self):
        result = validate_sql("SELECT 1 + 1 AS result;")
        assert result.passed is True

    # ── DML — MUST BLOCK ─────────────────────────────────────────────────────

    def test_block_delete(self):
        result = validate_sql("DELETE FROM users WHERE id = 1")
        assert result.passed is False
        assert "DELETE" in result.message or "forbidden" in result.message.lower()

    def test_block_update(self):
        result = validate_sql("UPDATE users SET name = 'hacked' WHERE id = 1")
        assert result.passed is False

    def test_block_insert(self):
        result = validate_sql("INSERT INTO users (name) VALUES ('attacker')")
        assert result.passed is False

    def test_block_insert_embedded(self):
        result = validate_sql("SELECT * FROM users; INSERT INTO admins VALUES (1)")
        assert result.passed is False

    # ── DDL — MUST BLOCK ─────────────────────────────────────────────────────

    def test_block_drop(self):
        result = validate_sql("DROP TABLE users")
        assert result.passed is False

    def test_block_alter(self):
        result = validate_sql("ALTER TABLE users ADD COLUMN evil TEXT")
        assert result.passed is False

    def test_block_create(self):
        result = validate_sql("CREATE TABLE evil AS SELECT * FROM users")
        assert result.passed is False

    def test_block_truncate(self):
        result = validate_sql("TRUNCATE TABLE orders")
        assert result.passed is False

    # ── PERMISSION COMMANDS — MUST BLOCK ─────────────────────────────────────

    def test_block_grant(self):
        result = validate_sql("GRANT ALL ON users TO attacker")
        assert result.passed is False

    def test_block_revoke(self):
        result = validate_sql("REVOKE SELECT ON users FROM analyst")
        assert result.passed is False

    # ── INJECTION PATTERNS — MUST BLOCK ──────────────────────────────────────

    def test_block_multiple_statements(self):
        result = validate_sql("SELECT 1; DROP TABLE users")
        assert result.passed is False

    def test_block_pg_read_file(self):
        result = validate_sql("SELECT pg_read_file('/etc/passwd')")
        assert result.passed is False

    def test_block_select_into_outfile(self):
        result = validate_sql("SELECT * FROM users INTO OUTFILE '/tmp/dump.csv'")
        assert result.passed is False

    # ── EDGE CASES ────────────────────────────────────────────────────────────

    def test_block_empty_sql(self):
        result = validate_sql("")
        assert result.passed is False

    def test_block_whitespace_only(self):
        result = validate_sql("   \n\t  ")
        assert result.passed is False

    def test_block_non_select_start(self):
        result = validate_sql("EXPLAIN SELECT * FROM users")
        assert result.passed is False

    def test_pass_with_keyword_in_string_literal(self):
        # "DELETE" inside a string should not trigger the block
        sql = "SELECT * FROM audit_log WHERE action = 'DELETE'"
        result = validate_sql(sql)
        assert result.passed is True

    def test_pass_with_drop_in_column_name(self):
        sql = "SELECT drop_date, reason FROM scheduled_maintenance"
        result = validate_sql(sql)
        assert result.passed is True
