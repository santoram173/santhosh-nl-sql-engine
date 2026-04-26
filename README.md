# Santhosh NL→SQL Engine

> A deterministic AI-powered SQL query engine. Natural language in  validated, safe SQL out. Every query passes through a 7-stage security pipeline where **the LLM generates but the backend enforces**.

[![CI](https://github.com/yourusername/santhosh-nl-sql-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/yourusername/santhosh-nl-sql-engine/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com)

---

## The Core Design Rule

```
LLM generates SQL.
Backend enforces LIMIT, read-only, and all safety rules.
LLM output is NEVER trusted for constraint enforcement.
```

This means:
- **LIMIT** is always injected by the executor — never by the LLM
- **Read-only** is enforced via `SET TRANSACTION READ ONLY` at the asyncpg level
- **DDL/DML blocking** is done by a rule-based AST scanner, not by prompting the LLM to "only write SELECT"
- A compromised or hallucinating LLM **cannot** bypass these constraints

---

## 7-Stage Pipeline

```
User Question
     │
     ▼  Stage 1 ── Ambiguity Check      ← Rule-based, blocks vague/injection queries
     │
     ▼  Stage 2 ── Schema Relevance     ← Fuzzy match against DB schema (difflib)
     │
     ▼  Stage 3 ── LLM Classifier       ← Gemini: VALID / INVALID intent
     │
     ▼  Stage 4 ── SQL Generation       ← Gemini: SQL with full schema context
     │
     ▼  Stage 5 ── Confidence Eval      ← Rule-based score + warnings (0.0–1.0)
     │
     ▼  Stage 6 ── SQL Validation       ← CRITICAL: blocks DDL/DML/injection (rule-based)
     │
     ▼  Stage 7 ── Execution            ← asyncpg: read-only tx, LIMIT enforced
     │
     ▼
  JSON Response
```

Each stage is a **hard gate** — failure stops the pipeline and returns a structured error identifying exactly which stage blocked the query and why.

---

## Quick Start

### Prerequisites
- Python 3.12+
- PostgreSQL 14+ (or Docker)
- [Google Gemini API key](https://ai.google.dev/)

### 1. Clone & Install

```bash
git clone https://github.com/yourusername/santhosh-nl-sql-engine.git
cd santhosh-nl-sql-engine

python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env: set GEMINI_API_KEY and DATABASE_URL
```

### 2. Set Up Database

```bash
# Option A: Use Docker (recommended)
docker-compose up postgres -d

# Option B: Local PostgreSQL
psql -U postgres -f scripts/init_db.sql
```

### 3. Run the Engine

```bash
uvicorn backend.main:app --reload --port 8000
```

- **Frontend UI:** http://localhost:8000
- **Swagger API docs:** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health

### 4. Docker (Full Stack)

```bash
# Copy and configure environment
cp .env.example .env
# Set GEMINI_API_KEY in .env

# Start PostgreSQL + backend
docker-compose up --build
```

---

## Example Queries

Try these in the UI or via API:

```
"Top 10 customers by total order value in the last 30 days"
"Daily revenue trend for the past week"
"Which products have the highest average order value?"
"Customers who placed more than 3 orders this month"
"Revenue breakdown by product category and country"
```

**Blocked by design:**
```
"Delete all customers"              → Stage 3 (classifier) or Stage 6 (validator)
"Drop the orders table"             → Stage 6 (SQL validation)
"Show me everything"                → Stage 1 (ambiguity)
"What is the weather in Toronto?"     → Stage 2 (schema relevance)
```

---

## Project Structure

```
santhosh-nl-sql-engine/
├── frontend/
│   └── index.html                    # Production UI (pure HTML/CSS/JS)
│
├── backend/
│   ├── main.py                       # FastAPI app + middleware
│   ├── config.py                     # Settings via pydantic-settings
│   │
│   ├── pipeline/
│   │   ├── orchestrator.py           # Runs all 7 stages in sequence
│   │   ├── stage1_ambiguity.py       # Rule-based vagueness detection
│   │   ├── stage2_schema_relevance.py # Fuzzy schema matching
│   │   ├── stage3_classifier.py      # LLM: VALID/INVALID classification
│   │   ├── stage4_sql_generation.py  # LLM: SQL generation
│   │   ├── stage5_confidence.py      # Rule-based quality scoring
│   │   ├── stage6_sql_validation.py  # CRITICAL: DDL/DML/injection blocking
│   │   └── stage7_executor.py        # asyncpg: read-only, LIMIT enforced
│   │
│   ├── routes/
│   │   ├── query.py                  # POST /query
│   │   ├── explain.py                # POST /explain
│   │   ├── schema.py                 # GET /schema
│   │   ├── session.py                # GET/DELETE /session/{id}
│   │   ├── admin.py                  # GET /admin/metrics, /admin/logs
│   │   └── health.py                 # GET /health
│   │
│   ├── services/
│   │   ├── gemini.py                 # GeminiProvider (retry, truncation detection)
│   │   ├── schema_cache.py           # MD5 fingerprint + TTL cache
│   │   ├── session_store.py          # Per-user session history (in-memory)
│   │   └── metrics.py                # In-memory metrics collector
│   │
│   ├── models/
│   │   └── schemas.py                # All Pydantic request/response models
│   │
│   ├── database/
│   │   └── pool.py                   # asyncpg pool init/teardown
│   │
│   └── utils/
│       └── logger.py                 # Structured logging setup
│
├── tests/
│   ├── unit/
│   │   ├── test_stage1_ambiguity.py
│   │   ├── test_stage2_schema_relevance.py
│   │   ├── test_stage5_confidence.py
│   │   ├── test_stage6_sql_validation.py
│   │   └── test_stage7_executor.py   # LIMIT injection tests
│   └── integration/
│       └── test_pipeline.py          # Full pipeline with mocked LLM/DB
│
├── docs/
│   ├── PIPELINE.md                   # Stage-by-stage architecture doc
│   └── API.md                        # Full API reference
│
├── scripts/
│   └── init_db.sql                   # Sample schema + seed data
│
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
├── CONTRIBUTING.md
├── CHANGELOG.md
└── LICENSE
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/query` | Run NL query through 7-stage pipeline |
| `POST` | `/explain` | Explain a SQL statement (on-demand) |
| `GET` | `/schema` | Database schema (cached, MD5 fingerprinted) |
| `GET` | `/session/{id}` | Session query history |
| `DELETE` | `/session/{id}` | Clear session history |
| `GET` | `/admin/metrics` | Engine metrics (queries, latency, blocks) |
| `GET` | `/admin/logs` | Recent logs (ring buffer) |
| `GET` | `/health` | DB + cache + LLM health check |

Full documentation: [docs/API.md](docs/API.md)

---

## Configuration

All configuration is via environment variables (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | required | Google Gemini API key |
| `DATABASE_URL` | required | PostgreSQL connection string |
| `MAX_RESULT_ROWS` | `1000` | **Hard cap enforced by executor (never LLM)** |
| `DEFAULT_LIMIT` | `100` | Injected when LLM omits LIMIT |
| `DB_COMMAND_TIMEOUT` | `30` | Query timeout in seconds |
| `SCHEMA_CACHE_TTL` | `300` | Schema cache TTL in seconds |
| `CONFIDENCE_BLOCK_THRESHOLD` | `0.3` | Min confidence score to allow execution |
| `SESSION_MAX_HISTORY` | `10` | Max interactions stored per session |
| `GEMINI_RETRY_ATTEMPTS` | `3` | LLM retry count on failure |

---

## Running Tests

```bash
# All tests
pytest

# Unit tests only (no DB or API key required)
pytest tests/unit/ -v

# With coverage report
pytest --cov=backend --cov-report=html
open htmlcov/index.html

# Single stage
pytest tests/unit/test_stage6_sql_validation.py -v
```

---

## Security Model

| Layer | Mechanism | What it prevents |
|---|---|---|
| Stage 1 | Rule-based pattern matching | Vague queries, NL injection probes |
| Stage 3 | LLM classification | Obvious write-intent queries |
| Stage 6 | AST keyword + pattern scanner | DDL, DML, system functions, multi-statement |
| Stage 7 | `SET TRANSACTION READ ONLY` | Any write that bypasses Stage 6 |
| Stage 7 | LIMIT injection | Full-table dump via unlimited SELECT |
| Stage 7 | `statement_timeout` | Runaway query DoS |
| DB | Read-only PostgreSQL role | Even if all app layers fail |

See [docs/PIPELINE.md](docs/PIPELINE.md) for the full security architecture.

---

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) first.  
Security issues: see [legal/SECURITY.md](legal/SECURITY.md) — do not open public GitHub issues.

---

## License

MIT — see [LICENSE](LICENSE).
