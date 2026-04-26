# Privacy Policy

**Santhosh NL→SQL Engine**
**Last updated: April 26, 2026**

---

## Data Processed

### Natural Language Queries
Your plain-English questions are processed through the pipeline. When Gemini API integration is enabled, query text and database schema metadata (table/column names) are transmitted to Google's Gemini API for intent classification and SQL generation.

### Database Schema Metadata
Table names, column names, and data types are cached in memory to provide context to the LLM. **Row data from your database is never sent to any LLM.**

### Query Logs
Query metadata is stored in an in-memory ring buffer (last 500 entries): timestamp, log level, and message. Query result rows are never logged.

### Session History
The last N queries per session are stored in memory (default: 10). Sessions are isolated — no cross-session data access. All history is lost on server restart.

---

## Third-Party Services

**Google Gemini API**: When AI features are used, query text and schema metadata are sent to Google. Review [Google's Privacy Policy](https://policies.google.com/privacy) and [Gemini API Terms](https://ai.google.dev/gemini-api/terms) before deploying with sensitive data.

---

## Self-Hosted Deployments

If you deploy this software, you are the data controller for all data your users process through it. You must provide your users with appropriate privacy notices covering the Gemini API transmission.

---

## Contact

Open an issue at: `https://github.com/yourusername/santhosh-nl-sql-engine/issues`
