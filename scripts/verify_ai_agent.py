#!/usr/bin/env python3
"""Manual live verification of the tool-using AI reconciliation agent.

Loads the three engine input files, runs the deterministic engine, then sends
one needs_human invoice through reconcile_ambiguous_case_with_tools() using
the real Claude API. invoices.json / ground_truth are never loaded.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

os.chdir(BACKEND_DIR)

from models.normalized import NormalizedInvoice  # noqa: E402
from models.result import DeterministicReconciliationResult  # noqa: E402
from services.agent_tools import AgentToolContext  # noqa: E402
from services.ai_agent import reconcile_ambiguous_case_with_tools  # noqa: E402
from services.ingestion import load_reconciliation_input  # noqa: E402
from services.matching import match_invoices_to_rate_cards  # noqa: E402
from services.normalization import normalize_reconciliation_input  # noqa: E402
from services.reconciliation import reconcile_input  # noqa: E402


def _invoice_by_id(
    invoices: list[NormalizedInvoice],
    invoice_id: str,
) -> NormalizedInvoice:
    for invoice in invoices:
        if invoice.raw.invoice_id == invoice_id:
            return invoice
    raise SystemExit(f"Invoice {invoice_id} was not found in the loaded engine input.")


def _build_case_context(
    invoice: NormalizedInvoice,
    result: DeterministicReconciliationResult,
    dispatch_payload: dict | None,
    matched_rate_card: dict | None,
) -> dict:
    deterministic_rupee_impact = round(result.rupee_impact, 2)
    return {
        "invoice_data": invoice.raw.model_dump(mode="json"),
        "normalized_invoice_data": {
            "invoice_id": invoice.raw.invoice_id,
            "lr_number": invoice.lr_number,
            "transporter_name": invoice.transporter_name,
            "origin": invoice.origin,
            "destination": invoice.destination,
            "vehicle_type": invoice.vehicle_type,
            "weight_billed_tons": invoice.weight_billed_tons,
            "rate_applied_per_ton": invoice.rate_applied_per_ton,
            "fixed_charge_applied": invoice.fixed_charge_applied,
            "total_amount": invoice.total_amount,
        },
        "matched_rate_card": matched_rate_card,
        "dispatch_record": dispatch_payload,
        "deterministic_checks_performed": list(result.checks_performed),
        "detected_ambiguity": result.explanation,
        "calculated_variance": {
            "weight_variance_pct": result.evidence.weight_variance_pct,
            "acceptable_weight_variance_pct": result.evidence.acceptable_weight_variance_pct,
        },
        "calculated_financial_impact": {
            "rupee_impact": deterministic_rupee_impact,
            "expected_amount": result.evidence.expected_amount,
            "billed_amount": result.evidence.billed_amount,
        },
        "rupee_impact": deterministic_rupee_impact,
        "relevant_evidence": [
            {
                "source": "invoice",
                "field": "invoice_id",
                "value": invoice.raw.invoice_id,
            },
            {
                "source": "invoice",
                "field": "lr_number",
                "value": invoice.lr_number,
            },
        ],
    }


def main() -> None:
    if not (os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")):
        raise SystemExit(
            "Claude API key is not configured. Set CLAUDE_API_KEY or ANTHROPIC_API_KEY "
            "before running this live verification script."
        )

    os.environ.setdefault("CLAUDE_TIMEOUT_SECONDS", "60")

    raw_input = load_reconciliation_input()
    normalized = normalize_reconciliation_input(raw_input)

    match_results = match_invoices_to_rate_cards(normalized.invoices, normalized.rate_cards)
    match_by_invoice_id = {item.invoice_id: item for item in match_results}

    summary = reconcile_input(normalized)

    print("DETERMINISTIC STATUS COUNTS")
    print(f"total invoices: {summary.total_invoices}")
    print(f"auto_clear: {summary.auto_clear}")
    print(f"flagged: {summary.flagged}")
    print(f"needs_human: {summary.needs_human}")

    needs_human = [item for item in summary.results if item.status == "needs_human"]
    if not needs_human:
        raise SystemExit("No invoice landed in needs_human; cannot exercise the AI agent.")

    chosen = needs_human[0]
    invoice = _invoice_by_id(normalized.invoices, chosen.invoice_id)
    match_result = match_by_invoice_id[chosen.invoice_id]
    matched_rate_card = (
        match_result.matched_rate_card.raw.model_dump(mode="json")
        if match_result.matched_rate_card is not None
        else None
    )
    dispatch_record = next(
        (
            record.raw.model_dump(mode="json")
            for record in normalized.dispatch_records
            if record.lr_number == invoice.lr_number
        ),
        None,
    )

    deterministic_rupee_impact = round(chosen.rupee_impact, 2)
    case_context = _build_case_context(
        invoice,
        chosen,
        dispatch_record,
        matched_rate_card,
    )
    tool_context = AgentToolContext(
        invoices=normalized.invoices,
        rate_cards=normalized.rate_cards,
        dispatch_records=normalized.dispatch_records,
    )

    print("\nSELECTED NEEDS_HUMAN INVOICE")
    print(f"invoice_id: {chosen.invoice_id}")
    print(f"lr_number: {chosen.lr_number}")
    print(f"discrepancy_type: {chosen.discrepancy_type}")
    print(f"deterministic_rupee_impact: {deterministic_rupee_impact}")
    print(f"matched_rate_id: {chosen.matched_rate_id}")
    print(f"explanation: {chosen.explanation}")

    print("\nCALLING reconcile_ambiguous_case_with_tools() — live Claude API")
    ai_response = reconcile_ambiguous_case_with_tools(
        case_context,
        tool_context=tool_context,
    )

    print("\nFULL AI STRUCTURED RESPONSE INCLUDING agent_trace")
    print(json.dumps(ai_response, indent=2, sort_keys=True, default=str))

    ai_rupee_impact = round(float(ai_response["rupee_impact"]), 2)
    print("\nRUPEE IMPACT CONFIRMATION")
    print(f"deterministic_rupee_impact_passed_in: {deterministic_rupee_impact}")
    print(f"ai_response_rupee_impact: {ai_rupee_impact}")
    if ai_rupee_impact == deterministic_rupee_impact:
        print(
            "CONFIRMED: AI rupee_impact exactly equals the deterministic rupee_impact "
            "passed in."
        )
    else:
        print(
            "MISMATCH: AI rupee_impact does not equal the deterministic rupee_impact "
            "passed in. The AI path used a different value (possibly a tool "
            "recalculation or a needs_human fallback)."
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
