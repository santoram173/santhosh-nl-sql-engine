# Security Policy

**Santhosh NL→SQL Engine**

---

## Supported Versions

| Version | Supported |
|---|---|
| `main` branch | ✅ Active |
| Latest release | ✅ Active |
| Older releases | ❌ Not supported |

---

## Security Architecture

The engine is designed with **defence in depth** — multiple independent layers block malicious or erroneous queries:

| Layer | What it enforces |
|---|---|
| Stage 1 (Ambiguity) | NL-level injection probes, malicious phrasing |
| Stage 3 (Classifier) | Intent-level: blocks obvious write requests |
| Stage 6 (SQL Validator) | **Critical gate** — blocks DDL/DML/system functions regardless of LLM output |
| Stage 7 (Executor) | `SET TRANSACTION READ ONLY`, LIMIT cap, timeout |
| PostgreSQL role | Read-only DB role as last line of defence |

**Key design guarantee:** Stage 6 is entirely rule-based and independent of the LLM. Even a fully compromised LLM cannot bypass it.

---

## Reporting a Vulnerability

**Do not open public GitHub issues for security vulnerabilities.**

1. Use [GitHub Security Advisories](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability) — click "Report a vulnerability" on the Security tab.

2. Include:
   - Description and impact
   - Component affected (which pipeline stage)
   - Steps to reproduce
   - Proof-of-concept (if applicable)
   - Suggested fix (optional)

**Response timeline:**
- Acknowledgement: within 48 hours
- Assessment: within 5 business days
- Fix: within 14 days for Critical/High
- Disclosure: 90-day coordinated disclosure

---

## Known Limitations

- **Stage 2 fuzzy matching** is approximate — very creatively phrased queries about unrelated domains may pass through to Stage 3
- **LLM prompt injection** via the NL question could potentially cause Stage 4 to generate incorrect (but syntactically valid SELECT) SQL — Stage 6 catches DML/DDL injection, but semantic confusion cannot be fully prevented
- **Confidence scoring** (Stage 5) is heuristic — it warns but may not catch all semantically incorrect queries

---

## Secure Deployment Checklist

- [ ] PostgreSQL role has `SELECT`-only privileges (see `scripts/init_db.sql`)
- [ ] `GEMINI_API_KEY` is stored as an env var, never in code
- [ ] `MAX_RESULT_ROWS` is set appropriately for your data volume
- [ ] TLS is enabled on the API endpoint
- [ ] API is behind authentication middleware in production
- [ ] `ALLOW_ORIGINS` in CORS is restricted to known domains
- [ ] Logs do not capture query result rows (they don't by default)
