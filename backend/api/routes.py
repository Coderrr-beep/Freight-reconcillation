import os
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from models.invoice import DispatchRecord, Invoice
from models.rate_card import RateCardEntry
from models.result import BatchResult
from services.ingestion import load_dispatch_records, load_invoices, load_rate_cards
from services.orchestrator import (
    get_batch_result,
    get_latest_batch,
    run_reconciliation_batch,
)

router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/health")
def api_health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/status")
def system_status() -> dict[str, str]:
    """Operational status for the control-plane UI. Does not run reconciliation."""
    llm_configured = bool(
        os.getenv("CLAUDE_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("GROQ_API_KEY")
    )
    return {
        "engine": "online",
        "ai_agent": "ready" if llm_configured else "degraded",
        "version": "1.0.0",
    }


@router.get("/api/invoices", response_model=list[Invoice])
def list_invoices() -> list[Invoice]:
    """Engine-input invoices (no ground-truth labels)."""
    return load_invoices()


@router.get("/api/dispatch-records", response_model=list[DispatchRecord])
def list_dispatch_records() -> list[DispatchRecord]:
    return load_dispatch_records()


@router.get("/api/rate-cards", response_model=list[RateCardEntry])
def list_rate_cards() -> list[RateCardEntry]:
    return load_rate_cards()


@router.post("/api/batches", response_model=BatchResult)
def run_batch() -> BatchResult:
    """Run ingest → deterministic engine → AI on needs_human cases."""
    batch_id = str(uuid4())
    return run_reconciliation_batch(batch_id)


@router.get("/api/batches/latest", response_model=BatchResult)
def latest_batch() -> BatchResult:
    batch = get_latest_batch()
    if batch is None:
        raise HTTPException(status_code=404, detail="No reconciliation batch has been run yet")
    return batch


@router.get("/api/batches/{batch_id}", response_model=BatchResult)
def fetch_batch(batch_id: str) -> BatchResult:
    batch = get_batch_result(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")
    return batch
