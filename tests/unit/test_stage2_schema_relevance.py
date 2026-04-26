"""Unit tests for Stage 2: Schema Relevance Check."""
import pytest
from backend.pipeline.stage2_schema_relevance import check_schema_relevance

SAMPLE_SCHEMA = {
    "tables": [
        {
            "name": "orders",
            "columns": [
                {"name": "id", "type": "integer"},
                {"name": "customer_id", "type": "integer"},
                {"name": "amount", "type": "numeric"},
                {"name": "created_at", "type": "timestamp"},
                {"name": "status", "type": "varchar"},
            ],
        },
        {
            "name": "customers",
            "columns": [
                {"name": "id", "type": "integer"},
                {"name": "name", "type": "varchar"},
                {"name": "email", "type": "varchar"},
                {"name": "country", "type": "varchar"},
            ],
        },
        {
            "name": "products",
            "columns": [
                {"name": "id", "type": "integer"},
                {"name": "title", "type": "varchar"},
                {"name": "price", "type": "numeric"},
                {"name": "category", "type": "varchar"},
            ],
        },
    ]
}


class TestSchemaRelevance:

    def test_pass_exact_table_match(self):
        result = check_schema_relevance("Show all orders from last week", SAMPLE_SCHEMA)
        assert result.passed is True

    def test_pass_exact_column_match(self):
        result = check_schema_relevance("What is the total amount by customer_id", SAMPLE_SCHEMA)
        assert result.passed is True

    def test_pass_fuzzy_match_customers(self):
        result = check_schema_relevance("List customers by country", SAMPLE_SCHEMA)
        assert result.passed is True

    def test_pass_fuzzy_match_products(self):
        result = check_schema_relevance("Show product categories and prices", SAMPLE_SCHEMA)
        assert result.passed is True

    def test_pass_partial_match(self):
        result = check_schema_relevance("How many customer emails are there?", SAMPLE_SCHEMA)
        assert result.passed is True

    def test_fail_completely_unrelated(self):
        # "pizza", "restaurant", "menu" have no match >= 0.65 against orders/customers/products schema
        result = check_schema_relevance("What pizza restaurants are near me right now?", SAMPLE_SCHEMA)
        assert result.passed is False

    def test_fail_unrelated_technical(self):
        # "kubernetes", "nginx", "deployment" have no match >= 0.65 against the schema
        result = check_schema_relevance("How do I configure nginx reverse proxy for kubernetes?", SAMPLE_SCHEMA)
        assert result.passed is False

    def test_pass_empty_schema_allows_through(self):
        """With no schema, stage should allow through (fail open)."""
        result = check_schema_relevance("Show orders from last month", {})
        assert result.passed is True
        assert result.data.get("schema_available") is False

    def test_pass_none_schema_allows_through(self):
        result = check_schema_relevance("revenue by category", None)
        assert result.passed is True

    def test_data_contains_top_matches(self):
        result = check_schema_relevance("customer orders by status", SAMPLE_SCHEMA)
        assert result.passed is True
        assert "top_matches" in result.data
        assert len(result.data["top_matches"]) > 0

    def test_fail_gibberish_query(self):
        # Pure random characters with no similarity to schema tokens at 0.65 threshold
        result = check_schema_relevance("qwzxjkplmvbnrty fghsda", SAMPLE_SCHEMA)
        assert result.passed is False
