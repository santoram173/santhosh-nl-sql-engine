# API Documentation

**Santhosh NL→SQL Engine v1.0.0**

Base URL: `http://localhost:8000`  
Interactive docs: `http://localhost:8000/docs` (Swagger UI)  
ReDoc: `http://localhost:8000/redoc`

---

## Endpoints

### `POST /query`

Run a natural language question through the full 7-stage pipeline.

**Request:**
```json
{
  "question": "Top 10 customers by total order value in the last 30 days",
  "session_id": "sess_abc123",
  "explain": false
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `question` | string | ✅ | Natural language query (1–500 chars) |
| `session_id` | string | ❌ | Session ID for history context (default: `"default"`) |
| `explain` | bool | ❌ | Include SQL explanation inline (default: `false`) |

**Success Response (200):**
```json
{
  "success": true,
  "question": "Top 10 customers by total order value in the last 30 days",
  "sql": "SELECT c.name, SUM(o.amount) AS total_value\nFROM customers c\nJOIN orders o ON c.id = o.customer_id\nWHERE o.created_at >= NOW() - INTERVAL '30 days'\nGROUP BY c.name\nORDER BY total_value DESC\nLIMIT 100",
  "rows": [
    {"name": "Alice Chen", "total_value": 4850.00},
    {"name": "Priya Nair", "total_value": 3200.00}
  ],
  "columns": ["name", "total_value"],
  "row_count": 2,
  "limit_enforced": true,
  "intent": "aggregate",
  "confidence": 0.95,
  "warnings": [],
  "explanation": null,
  "execution_time_ms": 87.4,
  "pipeline_stages": {
    "ambiguity":        {"passed": true, "message": "Query is clear and specific."},
    "schema_relevance": {"passed": true, "message": "Found 3 schema match(es)."},
    "classifier":       {"passed": true, "message": "Query classified as VALID (aggregate)"},
    "sql_generation":   {"passed": true, "message": "SQL generated successfully."},
    "confidence":       {"passed": true, "message": "Confidence: 95%"},
    "sql_validation":   {"passed": true, "message": "SQL passed all safety checks."},
    "execution":        {"passed": true, "message": "Executed successfully — 2 row(s) in 12.3ms."}
  }
}
```

**Pipeline Failure Response (200):**
```json
{
  "success": false,
  "question": "delete all users",
  "sql": null,
  "error": "Query classified as non-queryable: This question requests data modification, not retrieval.",
  "failed_stage": "LLM Classifier",
  "failed_stage_number": 3,
  "pipeline_stages": {
    "ambiguity":        {"passed": true, "message": "Query is clear and specific."},
    "schema_relevance": {"passed": true, "message": "Found 1 schema match(es)."},
    "classifier":       {"passed": false, "message": "Query classified as non-queryable..."},
    "sql_generation":   null,
    "confidence":       null,
    "sql_validation":   null,
    "execution":        null
  }
}
```

---

### `POST /explain`

Generate a plain-English explanation of a SQL statement.  
**Separate from `/query` by design — triggered on demand only.**

**Request:**
```json
{
  "sql": "SELECT c.name, SUM(o.amount) FROM customers c JOIN orders o ON c.id = o.customer_id GROUP BY c.name",
  "session_id": "sess_abc123"
}
```

**Response:**
```json
{
  "sql": "SELECT c.name, SUM(o.amount) ...",
  "explanation": "This query retrieves each customer's name and calculates their total order value by joining the customers and orders tables. It groups the results by customer name so each customer appears once, and the SUM function adds up all their order amounts. The results will show one row per customer with their name and total spending.",
  "session_id": "sess_abc123"
}
```

---

### `GET /schema`

Return the cached database schema.

**Query params:**
- `refresh=true` — force an immediate schema refresh (bypasses cache)

**Response:**
```json
{
  "tables": [
    {
      "name": "customers",
      "columns": [
        {"name": "id",         "type": "integer", "nullable": false},
        {"name": "name",       "type": "character varying", "nullable": false},
        {"name": "email",      "type": "character varying", "nullable": true},
        {"name": "country",    "type": "character varying", "nullable": true},
        {"name": "created_at", "type": "timestamp with time zone", "nullable": true}
      ],
      "row_count": 10
    }
  ],
  "fingerprint": "a3f8b2c1",
  "cached_at": "2026-04-25T10:30:00"
}
```

---

### `GET /session/{session_id}`

Retrieve query history for a session.

**Response:**
```json
{
  "session_id": "sess_abc123",
  "history_count": 2,
  "history": [
    {
      "question": "Total revenue by month",
      "sql": "SELECT DATE_TRUNC('month', created_at)...",
      "intent": "aggregate",
      "row_count": 12
    }
  ]
}
```

### `DELETE /session/{session_id}`

Clear all history for a session.

**Response:**
```json
{"cleared": true, "session_id": "sess_abc123"}
```

---

### `GET /admin/metrics`

Engine performance metrics.

**Response:**
```json
{
  "total_queries": 142,
  "successful_queries": 128,
  "blocked_queries": 11,
  "failed_queries": 3,
  "success_rate": 90.1,
  "avg_latency_ms": 1243.5,
  "stage_block_counts": {
    "ambiguity": 4,
    "schema_relevance": 2,
    "classifier": 3,
    "sql_validation": 2
  }
}
```

---

### `GET /admin/logs`

Recent application logs from the in-memory ring buffer.

**Query params:**
- `limit` — number of entries (default: 50, max: 500)
- `level` — filter by level: `INFO`, `WARN`, `ERROR`

**Response:**
```json
{
  "logs": [
    {
      "timestamp": "2026-04-25T10:31:22",
      "level": "INFO",
      "message": "backend.pipeline.orchestrator: Query returned 12 rows in 87ms",
      "extra": {"logger": "backend.pipeline.orchestrator"}
    }
  ],
  "total": 1
}
```

---

### `GET /health`

Liveness and readiness check for all components.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "components": {
    "database": {"status": "healthy", "message": "Connection OK"},
    "schema_cache": {
      "status": "healthy",
      "tables": 5,
      "fingerprint": "a3f8b2c1",
      "cached_at": "2026-04-25T10:30:00"
    },
    "llm": {
      "status": "configured",
      "model": "gemini-1.5-pro",
      "total_calls": 142
    }
  }
}
```

---

## Error Codes

| HTTP Status | Meaning |
|---|---|
| `200` | Success (check `success` field in body for pipeline result) |
| `422` | Validation error — request body is malformed |
| `500` | Unhandled internal error |

Note: Pipeline failures (blocked stages) return HTTP `200` with `"success": false`. HTTP errors (4xx/5xx) indicate problems with the request or server, not pipeline decisions.
