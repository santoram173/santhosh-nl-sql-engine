"""Request and response models."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ── REQUESTS ──────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, description="Natural language query")
    session_id: str = Field(default="default", description="Session identifier")
    explain: bool = Field(default=False, description="Include SQL explanation inline")


class ExplainRequest(BaseModel):
    sql: str = Field(..., description="SQL statement to explain")
    session_id: str = Field(default="default")


class SessionClearRequest(BaseModel):
    session_id: str


# ── PIPELINE STAGE RESULT ─────────────────────────────────────────────────────

class StageResult(BaseModel):
    passed: bool
    message: str = ""
    data: Dict[str, Any] = {}


# ── RESPONSES ─────────────────────────────────────────────────────────────────

class QueryResponse(BaseModel):
    success: bool
    question: str
    sql: Optional[str] = None
    rows: Optional[List[Dict[str, Any]]] = None
    columns: Optional[List[str]] = None
    row_count: Optional[int] = None
    limit_enforced: bool = False
    intent: Optional[str] = None
    confidence: Optional[float] = None
    warnings: List[str] = []
    explanation: Optional[str] = None
    execution_time_ms: Optional[float] = None
    pipeline_stages: Dict[str, StageResult] = {}
    error: Optional[str] = None
    failed_stage: Optional[str] = None
    failed_stage_number: Optional[int] = None


class ExplainResponse(BaseModel):
    sql: str
    explanation: str
    session_id: str


class SchemaColumn(BaseModel):
    name: str
    type: str
    nullable: bool = True


class SchemaTable(BaseModel):
    name: str
    columns: List[SchemaColumn]
    row_count: Optional[int] = None


class SchemaResponse(BaseModel):
    tables: List[SchemaTable]
    fingerprint: str
    cached_at: str


class SessionInfo(BaseModel):
    session_id: str
    history_count: int
    history: List[Dict[str, Any]] = []


class MetricsResponse(BaseModel):
    total_queries: int
    successful_queries: int
    blocked_queries: int
    failed_queries: int
    success_rate: float
    avg_latency_ms: float
    stage_block_counts: Dict[str, int]


class LogEntry(BaseModel):
    timestamp: str
    level: str
    message: str
    extra: Dict[str, Any] = {}


class LogsResponse(BaseModel):
    logs: List[LogEntry]
    total: int
