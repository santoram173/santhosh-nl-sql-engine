"""Unit tests for Stage 1: Ambiguity Check."""
import pytest
from backend.pipeline.stage1_ambiguity import check_ambiguity


class TestAmbiguityCheck:

    def test_pass_clear_query(self):
        result = check_ambiguity("Show me total revenue by product category for last month")
        assert result.passed is True

    def test_pass_specific_query(self):
        result = check_ambiguity("Top 10 customers by order count in 2025")
        assert result.passed is True

    def test_fail_too_short_one_word(self):
        result = check_ambiguity("data")
        assert result.passed is False
        assert "short" in result.message.lower() or "specific" in result.message.lower()

    def test_fail_too_short_two_words(self):
        result = check_ambiguity("show me")
        assert result.passed is False

    def test_fail_vague_show_data(self):
        result = check_ambiguity("show me all data")
        assert result.passed is False

    def test_fail_vague_get_everything(self):
        result = check_ambiguity("get everything")
        assert result.passed is False

    def test_fail_only_stopwords(self):
        result = check_ambiguity("the a an is are")
        assert result.passed is False

    def test_fail_sql_injection_attempt(self):
        result = check_ambiguity("select users; drop table users")
        assert result.passed is False

    def test_fail_injection_with_comment(self):
        result = check_ambiguity("show orders -- drop table orders")
        assert result.passed is False

    def test_pass_with_filters(self):
        result = check_ambiguity("How many orders were placed in the last 7 days by country?")
        assert result.passed is True

    def test_pass_complex_query(self):
        result = check_ambiguity("Average order value grouped by customer segment over the past quarter")
        assert result.passed is True

    def test_pass_data_includes_word_count(self):
        result = check_ambiguity("Total sales by region for Q1 2025")
        assert result.passed is True
        assert "word_count" in result.data
        assert result.data["word_count"] >= 3
