# Freight Invoice Reconciliation Repository Handoff

## 1. Project Overview

This repository implements a freight-invoice reconciliation system. It loads invoices, contracted rate cards, and dispatch records, normalizes their fields, matches invoices to contracts, detects duplicate LR numbers, and deterministically classifies each invoice as `auto_clear`, `flagged`, or `needs_human`. Ambiguous cases can be sent to a Claude-preferred, Groq-fallback AI review layer that may inspect only controlled invoice, rate-card, dispatch, calculation, and historical-invoice tools. A FastAPI backend exposes health, source-data, and reconciliation-batch endpoints, while the frontend consumes those APIs.

## 2. Repository Tree

```text
backend/
  api/
    __init__.py
    routes.py
  main.py
  models/
    __init__.py
    duplicate.py
    input.py
    invoice.py
    matching.py
    normalized.py
    rate_card.py
    result.py
  services/
    __init__.py
    agent_tools.py
    ai_agent.py
    duplicate_detector.py
    ingestion.py
    matching.py
    normalization.py
    orchestrator.py
    reconciliation.py
    scoring.py
  tests/
    __init__.py
    test_agent_tools.py
    test_ai_agent.py
    test_ai_agent_tools.py
    test_ai_agent_tools_live.py
    test_duplicate_detector.py
    test_end_to_end_reconciliation.py
    test_matching.py
    test_normalization.py
    test_orchestrator.py
    test_reconciliation.py
    test_scoring.py
  validate_ingestion.py

data/
  dispatch_records.json
  invoices_for_engine.json
  invoices.json
  rate_card.json

frontend/
  index.html
  package.json
  src/
  ...

scripts/
  generate_synthetic_data.py
  verify_ai_agent.py
```

The requested Python file command is:

```sh
find . -type f -name "*.py" | grep -v __pycache__ | grep -v ".venv" | sort
```

## 3. Application Responsibilities

### Models

The files under `backend/models/` define Pydantic models for raw invoices, rate cards, dispatch records, normalized records, rate-card matches, duplicate detection, reconciliation evidence, deterministic results, AI results, merged results, and batch summaries.

### Ingestion

`backend/services/ingestion.py` reads and validates exactly these engine inputs:

- `data/rate_card.json`
- `data/invoices_for_engine.json`
- `data/dispatch_records.json`

It intentionally excludes `data/invoices.json`, which contains ground-truth labels for scoring.

### Normalization

`backend/services/normalization.py` creates normalized views while preserving raw records. It normalizes transporter names, routes, vehicle types, LR numbers, numbers, monetary values, weights, and dates.

### Matching

`backend/services/matching.py` matches invoices to rate cards. Origin, destination, and vehicle type must match exactly. Transporter names are matched exactly after normalization or through RapidFuzz fuzzy matching. Fuzzy matches require a score of at least `85.0` and a margin of at least `5.0` over the next candidate.

### Duplicate Detection

`backend/services/duplicate_detector.py` groups normalized invoices by LR number. A unique LR is marked `unique`. A repeated LR creates a duplicate case. The earliest invoice by invoice date and invoice ID is marked `duplicate_original`; later invoices are marked `potential_duplicate`.

### Deterministic Reconciliation

`backend/services/reconciliation.py` performs the authoritative calculations:

- rate-card comparison
- expected-amount calculation
- weight-variance calculation
- duplicate-LR detection
- rupee-impact calculation
- status classification

The deterministic statuses are `auto_clear`, `flagged`, and `needs_human`.

### AI Review

`backend/services/ai_agent.py` contains the Claude/Groq integration. It validates structured AI results, requires evidence for conclusive decisions, prevents invented evidence, preserves deterministic financial impact, and falls back to `needs_human` for configuration, API, tool, validation, or iteration-limit failures.

### Controlled Agent Tools

`backend/services/agent_tools.py` exposes only these tools:

- `get_invoice`
- `get_rate_card`
- `get_dispatch_record`
- `calculate_weight_variance`
- `calculate_financial_impact`
- `search_similar_invoices`

Tool arguments are validated with Pydantic. Unknown tools and invalid arguments are rejected.

### Orchestration

`backend/services/orchestrator.py` runs the deterministic engine first, sends only `needs_human` cases to the AI layer, merges the results, computes batch totals, sorts results by invoice ID, and stores the batch in an in-memory dictionary.

### API

`backend/main.py` creates the FastAPI application and enables CORS for the local frontend development ports.

`backend/api/routes.py` exposes:

- `GET /`
- `GET /health`
- `GET /api/health`
- `GET /api/status`
- `GET /api/invoices`
- `GET /api/dispatch-records`
- `GET /api/rate-cards`
- `POST /api/batches`
- `GET /api/batches/latest`
- `GET /api/batches/{batch_id}`

## 4. End-to-End Data Flow

The entry point is `run_reconciliation_batch(batch_id)` in `backend/services/orchestrator.py`.

1. `load_reconciliation_input()` loads and validates the three engine JSON files.
2. `normalize_reconciliation_input()` produces normalized invoice, rate-card, and dispatch records.
3. `reconcile_input()` performs the deterministic pass.
4. `match_invoices_to_rate_cards()` finds exact or reliable fuzzy rate-card matches.
5. `detect_duplicate_lrs()` groups invoices by normalized LR number.
6. `reconcile_invoice()` evaluates contract availability, rate mismatch, weight variance, duplicate billing, expected amount, rupee impact, and final status.
7. Deterministic `auto_clear` and `flagged` results are wrapped unchanged with `resolved_by="deterministic"`.
8. Deterministic `needs_human` results are passed to `reconcile_ambiguous_case_with_tools()`.
9. The selected LLM may use only the registered controlled tools and only for a maximum of five tool iterations.
10. The selected LLM's decision is mapped from `clear`, `flag`, or `needs_human` to `auto_clear`, `flagged`, or `needs_human`.
11. AI-resolved results use `resolved_by="ai_agent"`.
12. Results are sorted by invoice ID, aggregate counts are calculated, and a `BatchResult` is stored in `_BATCHES`.

The AI cannot access the filesystem, execute arbitrary code, invent evidence, invent contracts, invent historical invoices, or override deterministic rupee impact. If the selected provider cannot produce a safe validated result, the case remains `needs_human`.

## 5. Current Test Status

The root-level command from the original request was:

```sh
./.venv/bin/python -m pytest -v
```

That path does not exist in this workspace. The available environment is `backend/.venv`. Run the tests with:

```sh
cd backend
./.venv/bin/python -m pytest -v
```

Current result:

```text
79 tests collected
75 passed
3 failed
1 skipped
```

Failed tests:

```text
tests/test_duplicate_detector.py::TestOneDuplicateLR::test_one_duplicate_lr_flags_both_invoices
tests/test_duplicate_detector.py::TestMultipleInvoicesSameLR::test_three_invoices_with_same_lr
tests/test_end_to_end_reconciliation.py::test_engine_reconciles_synthetic_inputs_end_to_end
```

The duplicate tests disagree with the current implementation's `duplicate_original` behavior. The end-to-end test's expected aggregate values disagree with the current deterministic output.

Current end-to-end output includes:

```text
total invoices: 90
auto_clear count: 63
flagged count: 22
needs_human count: 5
rate mismatch count: 14
weight variance count: 4
duplicate count: 4
no contract count: 5
total ₹ impact: ₹113,293.24
```

The live Groq test is skipped unless live-test configuration is enabled and `GROQ_API_KEY` is configured.

## 6. Data Files

### `data/rate_card.json`

Total records: `27`

First record:

```json
{
  "rate_id": "RC001",
  "transporter": "Ashok Transport Co.",
  "origin": "Coimbatore",
  "destination": "Bengaluru",
  "vehicle_type": "16-ton truck",
  "rate_per_ton": 1402.35,
  "fixed_charge": 1176.7,
  "acceptable_weight_variance_pct": 3.0
}
```

Second record:

```json
{
  "rate_id": "RC002",
  "transporter": "Ashok Transport Co.",
  "origin": "Coimbatore",
  "destination": "Chennai",
  "vehicle_type": "10-ton truck",
  "rate_per_ton": 1292.87,
  "fixed_charge": 531.78,
  "acceptable_weight_variance_pct": 3.0
}
```

### `data/invoices_for_engine.json`

Total records: `90`

First record:

```json
{
  "invoice_id": "INV0020",
  "lr_number": "LR842225",
  "transporter_name": "Bharat Roadlines",
  "origin": "Ludhiana",
  "destination": "Delhi",
  "vehicle_type": "20-ton trailer",
  "weight_billed_tons": 3.11,
  "rate_applied_per_ton": 1302.79,
  "fixed_charge_applied": 1307.13,
  "total_amount": 5358.81,
  "invoice_date": "2026-07-11"
}
```

Second record:

```json
{
  "invoice_id": "INV0053",
  "lr_number": "LR176066",
  "transporter_name": "Bharat Roadlines",
  "origin": "Pune",
  "destination": "Mumbai",
  "vehicle_type": "20-ton trailer",
  "weight_billed_tons": 16.94,
  "rate_applied_per_ton": 1283.01,
  "fixed_charge_applied": 1204.57,
  "total_amount": 22938.76,
  "invoice_date": "2026-06-01"
}
```

### `data/dispatch_records.json`

Total records: `86`

First record:

```json
{
  "lr_number": "LR132938",
  "dispatched_weight_tons": 6.43
}
```

Second record:

```json
{
  "lr_number": "LR161324",
  "dispatched_weight_tons": 6.27
}
```

### `data/invoices.json`

Total records: `90`

This file has the same invoice fields as the engine input plus a `ground_truth` object containing `is_discrepancy`, `type`, `expected_action`, and `rupee_impact`. It is used for scoring and validation, not normal ingestion.

## 7. Known Issues and Limitations

- The repository root has no `.venv`; use `backend/.venv`.
- Three tests currently fail.
- Duplicate detection marks the earliest invoice in a repeated LR group as `duplicate_original`, while two tests expect all invoices to count as potential duplicates.
- Synthetic end-to-end expected aggregate values do not match the current deterministic output.
- The batch store is process-local memory and is lost when the backend stops.
- AI review prefers Claude when `CLAUDE_API_KEY` or `ANTHROPIC_API_KEY` is set, and otherwise uses Groq with `GROQ_API_KEY` and model `llama-3.3-70b-versatile`.
- The AI tool loop is limited to five iterations.
- The AI is not authoritative for arithmetic or rupee impact.
- `data/invoices.json` is excluded from engine ingestion by design.
- No git history is available in the supplied workspace, so recent commits could not be inspected.

## 8. Exact Source Files

The complete, unmodified source is stored in the repository itself in this order:

1. `backend/models/*.py`
2. `backend/services/ingestion.py`
3. `backend/services/normalization.py`
4. `backend/services/matching.py`
5. `backend/services/duplicate_detector.py`
6. `backend/services/reconciliation.py`
7. `backend/services/agent_tools.py`
8. `backend/services/ai_agent.py`
9. `backend/services/orchestrator.py`
10. `backend/services/scoring.py`
11. `backend/api/*.py`
12. `backend/main.py`

This document intentionally links to those source files instead of copying them, so the handoff remains maintainable and the source stays exactly authoritative on disk.
