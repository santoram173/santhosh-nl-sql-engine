# Pipeline Architecture

**Santhosh NL→SQL Engine — 7-Stage Validation Pipeline**

---

## Design Philosophy

> **LLMs generate. Backends enforce.**

The fundamental design rule of this engine: the LLM is a SQL *suggester*, not a safety enforcer. Every constraint that matters — LIMIT caps, read-only access, injection prevention — is enforced at the backend level, independent of what the LLM produces.

This means even if the LLM is compromised, hallucinating, or produces malicious SQL due to a prompt injection attack, the pipeline will block it before it reaches the database.

---

## Pipeline Diagram

```
User Question (plain English)
          │
          ▼
┌─────────────────────────────┐
│  Stage 1: Ambiguity Check   │  Rule-based
│  (stage1_ambiguity.py)      │  • Min word count
│                             │  • Vague pattern detection
│                             │  • Injection probe detection
└─────────────────────────────┘
          │ PASS
          ▼
┌─────────────────────────────┐
│  Stage 2: Schema Relevance  │  Fuzzy matching
│  (stage2_schema_relevance)  │  • Token extraction
│                             │  • difflib SequenceMatcher
│                             │  • Configurable threshold
└─────────────────────────────┘
          │ PASS
          ▼
┌─────────────────────────────┐
│  Stage 3: LLM Classifier    │  LLM (cheap, short prompt)
│  (stage3_classifier.py)     │  • VALID / INVALID label
│                             │  • Intent extraction
│                             │  • Fail-open for uptime
└─────────────────────────────┘
          │ VALID
          ▼
┌─────────────────────────────┐
│  Stage 4: SQL Generation    │  LLM (main generation)
│  (stage4_sql_generation.py) │  • Full schema context
│                             │  • Session history context
│                             │  • Markdown stripping
└─────────────────────────────┘
          │ SQL string
          ▼
┌─────────────────────────────┐
│  Stage 5: Confidence Eval   │  Rule-based
│  (stage5_confidence.py)     │  • SELECT * detection
│                             │  • Missing WHERE detection
│                             │  • Cartesian join risk
│                             │  • Score 0.0–1.0
└─────────────────────────────┘
          │ PASS (with optional warnings)
          ▼
┌─────────────────────────────┐
│  Stage 6: SQL Validation    │  Rule-based (CRITICAL GATE)
│  (stage6_sql_validation.py) │  • AST keyword scan
│                             │  • DDL / DML block
│                             │  • Pattern injection block
│                             │  • Multi-statement block
└─────────────────────────────┘
          │ PASS
          ▼
┌─────────────────────────────┐
│  Stage 7: Execution         │  asyncpg
│  (stage7_executor.py)       │  • LIMIT injection (ALWAYS)
│                             │  • Read-only transaction
│                             │  • statement_timeout
│                             │  • Row serialisation
└─────────────────────────────┘
          │
          ▼
    Structured JSON Response
```

---

## Stage Details

### Stage 1 — Ambiguity Check

**Type:** Rule-based  
**File:** `backend/pipeline/stage1_ambiguity.py`

Catches questions too vague to generate reliable SQL:

| Check | Example Blocked | Reason |
|---|---|---|
| Min word count | `"data"` | Fewer than 3 meaningful words |
| Vague pattern | `"show me everything"` | Matches vague regex patterns |
| Stop-word-only | `"the a an is"` | No meaningful content after removal |
| Injection probe | `"users; drop table"` | SQL injection attempt in NL query |
| Max length | >500 chars | Prevents prompt stuffing |

**Why rule-based?** Pattern matching is deterministic, fast (< 1ms), and free. Using an LLM for this check would add latency and cost for questions the engine should reject without even calling an LLM.

---

### Stage 2 — Schema Relevance Check

**Type:** Fuzzy matching (difflib)  
**File:** `backend/pipeline/stage2_schema_relevance.py`

Verifies the question references entities that exist in the database schema. Uses Python's `difflib.SequenceMatcher` for fuzzy matching — no ML required.

**Algorithm:**
1. Tokenise the question, remove stop words
2. Extract all table names + column names from schema (including `snake_case` parts)
3. Compute pairwise similarity between query tokens and schema tokens
4. Pass if any pair exceeds the threshold (default: 0.3)

**Fail-open behaviour:** If no schema is loaded (DB offline at startup), stage passes to avoid false negatives. Stage 7 will fail gracefully if the DB is truly unavailable.

---

### Stage 3 — LLM Classifier

**Type:** LLM (Gemini, short prompt)  
**File:** `backend/pipeline/stage3_classifier.py`

Asks Gemini to classify the question as `VALID` or `INVALID`. Uses a structured response format for deterministic parsing:

```
CLASSIFICATION: VALID|INVALID
INTENT: aggregate|filter|ranking|time_series|lookup|join|count
REASONING: one sentence
```

**Temperature:** `0.0` — deterministic classification.  
**Fail-open:** If the classifier API call fails, the stage passes (fail-open). Stage 6 remains the true safety gate, so uptime is not sacrificed for classifier availability.

---

### Stage 4 — SQL Generation

**Type:** LLM (Gemini, full schema context)  
**File:** `backend/pipeline/stage4_sql_generation.py`

Generates SQL using the full schema context + last 3 session interactions for continuity.

**System prompt rules:**
- Generate only `SELECT` statements
- Do NOT include `LIMIT` (executor handles this)
- Use exact table/column names from schema
- Use `NOW() - INTERVAL` for time references
- Return raw SQL only — no markdown, no explanation

**Output sanitisation:** Markdown fences, `sql:` prefixes, and trailing semicolons are stripped before the output reaches Stage 5.

---

### Stage 5 — Confidence Evaluation

**Type:** Rule-based scoring  
**File:** `backend/pipeline/stage5_confidence.py`

Scores the generated SQL from 0.0 to 1.0. Collects warnings passed to the API response. Only blocks if score is below `CONFIDENCE_BLOCK_THRESHOLD` (default: 0.3).

| Signal | Score Penalty | Warning? |
|---|---|---|
| `SELECT *` | -0.10 | Yes |
| No WHERE clause | -0.15 | Yes |
| Cartesian JOIN risk | -0.30 | Yes |
| Deep subquery nesting | -0.10 | Yes |
| Non-sargable predicates | -0.10 | Yes |
| SQL too short | -0.20 | Yes |
| Monthly query, no GROUP BY | -0.15 | Yes |

---

### Stage 6 — SQL Validation *(Critical Safety Gate)*

**Type:** Rule-based (deterministic)  
**File:** `backend/pipeline/stage6_sql_validation.py`

The most important stage. Enforces safety rules **independently of the LLM**. Even if the LLM is compromised or produces malicious SQL, this stage blocks it.

**What it blocks:**

| Category | Keywords |
|---|---|
| DML | `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `UPSERT` |
| DDL | `DROP`, `ALTER`, `CREATE`, `TRUNCATE` |
| Permissions | `GRANT`, `REVOKE` |
| System access | `EXECUTE`, `EXEC`, `CALL`, `COPY`, `VACUUM` |
| pg_* functions | `pg_read_file`, `pg_write_file`, `dblink`, `lo_export` |
| Injection patterns | `;` multi-statement, `INTO OUTFILE`, `xp_*` |

**String literal stripping:** Before keyword detection, single-quoted string literals are replaced with `''`. This prevents false positives (e.g. `WHERE action = 'DELETE'` should not block the query) while also preventing bypass attempts (e.g. `WHERE 1=1; DROP` in a literal).

---

### Stage 7 — Execution

**Type:** asyncpg  
**File:** `backend/pipeline/stage7_executor.py`

**LIMIT injection** (enforced here, never by the LLM):

```python
def _inject_limit(sql, max_rows, default_limit):
    if no LIMIT present:
        append LIMIT {default_limit}
    elif existing LIMIT > max_rows:
        replace with LIMIT {max_rows}
    # else: leave as-is
```

**Read-only transaction:**
```python
async with conn.transaction():
    await conn.execute("SET TRANSACTION READ ONLY")
    await conn.execute(f"SET statement_timeout = '{timeout * 1000}'")
    records = await conn.fetch(safe_sql)
```

Even if Stage 6 misses something, `SET TRANSACTION READ ONLY` means PostgreSQL will reject any write attempt at the protocol level — a second line of defence.

---

## Error Response Structure

When any stage fails:

```json
{
  "success": false,
  "question": "user's original question",
  "error": "Human-readable explanation of why this was blocked",
  "failed_stage": "SQL Validation",
  "failed_stage_number": 6,
  "pipeline_stages": {
    "ambiguity":        {"passed": true, "message": "Query is clear"},
    "schema_relevance": {"passed": true, "message": "2 matches found"},
    "classifier":       {"passed": true, "message": "VALID (aggregate)"},
    "sql_generation":   {"passed": true, "message": "SQL generated"},
    "confidence":       {"passed": true, "message": "85% confidence"},
    "sql_validation":   {"passed": false, "message": "Contains DELETE"},
    "execution":        null
  }
}
```

---

## Configuration

| Variable | Default | Enforced By |
|---|---|---|
| `MAX_RESULT_ROWS` | 1000 | Stage 7 (executor) |
| `DEFAULT_LIMIT` | 100 | Stage 7 (executor) |
| `DB_COMMAND_TIMEOUT` | 30s | Stage 7 (asyncpg) |
| `CONFIDENCE_BLOCK_THRESHOLD` | 0.3 | Stage 5 |
| `FUZZY_MATCH_THRESHOLD` | 0.3 | Stage 2 |
| `AMBIGUITY_MIN_WORDS` | 3 | Stage 1 |
| `SCHEMA_CACHE_TTL` | 300s | SchemaCache |
