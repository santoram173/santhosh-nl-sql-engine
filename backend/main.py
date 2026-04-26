"""
Santhosh NL→SQL Engine — FastAPI Application
============================================
7-stage deterministic SQL pipeline. LLM outputs are never trusted
for safety enforcement — all constraints are applied at the backend level.
"""
from contextlib import asynccontextmanager
import logging
import time
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.database.pool import init_pool, close_pool
from backend.services.schema_cache import SchemaCache
from backend.services.metrics import MetricsCollector
from backend.routes import query, explain, schema, session, admin, health
from backend.utils.logger import setup_logging
from backend.config import get_settings

setup_logging()
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_settings()
    log.info("Starting Santhosh NL→SQL Engine (env=%s)…", cfg.app_env)
    await init_pool()
    await SchemaCache.get_instance().refresh()
    MetricsCollector.get_instance()
    log.info("Engine ready — 7-stage pipeline active")
    yield
    log.info("Shutting down engine…")
    await close_pool()


app = FastAPI(
    title="Santhosh NL→SQL Engine",
    description=(
        "Deterministic AI-powered SQL query engine with a 7-stage validation pipeline.\n\n"
        "**LLM NEVER enforces:** LIMIT, read-only, or safety rules.\n"
        "**Backend ALWAYS enforces:** all constraints at the executor layer."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["X-Response-Time-Ms"] = str(ms)
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.exception("Unhandled exception on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error", "detail": str(exc)},
    )


app.include_router(health.router, tags=["Health"])
app.include_router(query.router, tags=["Query"])
app.include_router(explain.router, tags=["Explain"])
app.include_router(schema.router, tags=["Schema"])
app.include_router(session.router, tags=["Session"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])

frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
