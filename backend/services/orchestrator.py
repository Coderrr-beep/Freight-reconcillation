"""Top-level batch pipeline: deterministic engine first, AI agent only for
invoices the deterministic engine could not conclusively resolve.

This module does not modify matching.py, reconciliation.py, or ai_agent.py.
It only orchestrates calls to them and merges their outputs.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from models.input import ReconciliationInput
from models.invoice import DispatchRecord, Invoice
from models.rate_card import RateCardEntry
from models.result import (
    BatchResult,
    DeterministicReconciliationResult,
    MergedInvoiceResult,
    ReconciliationStatus,
)
from services.agent_tools import AgentToolContext
from services.ai_agent import AIReconciliationResult, reconcile_ambiguous_case_with_tools
from services.ingestion import load_reconciliation_input
from services.normalization import normalize_reconciliation_input
from services.reconciliation import reconcile_input

# In-memory batch store for the hackathon — no database needed.
_BATCHES: dict[str, BatchResult] = {}


def _map_ai_decision_to_status(decision: str) -> ReconciliationStatus:
    """Map the AI agent's decision vocabulary onto the engine's status vocabulary.

    Falls back to 'needs_human' for any unexpected value rather than raising,
    consistent with the "batch must never crash because of AI" rule.
    """
    mapping: dict[str, ReconciliationStatus] = {
        "clear": "auto_clear",
        "flag": "flagged",
        "needs_human": "needs_human",
    }
    return mapping.get(decision, "needs_human")


def _find_invoice(invoices: list[Invoice], invoice_id: str) -> Invoice | None:
    return next((inv for inv in invoices if inv.invoice_id == invoice_id), None)


def _find_rate_card(
    rate_cards: list[RateCardEntry], rate_id: str | None
) -> RateCardEntry | None:
    if rate_id is None:
        return None
    return next((rc for rc in rate_cards if rc.rate_id == rate_id), None)


def _find_dispatch_record(
    dispatch_records: list[DispatchRecord], lr_number: str
) -> DispatchRecord | None:
    return next((dr for dr in dispatch_records if dr.lr_number == lr_number), None)


def _find_normalized_invoice(tool_context: AgentToolContext, invoice_id: str) -> Any | None:
    return next(
        (inv for inv in tool_context.invoices if inv.raw.invoice_id == invoice_id),
        None,
    )


def _detected_ambiguity(deterministic_result: DeterministicReconciliationResult) -> str:
    """Synthesize a human-readable ambiguity description for the AI agent.

    Deliberately does not hardcode the full set of EngineDiscrepancyType
    values — it works for any current or future discrepancy_type by folding
    the deterministic engine's own explanation into the description.
    """
    return (
        f"Deterministic engine could not conclusively resolve this case "
        f"(discrepancy_type={deterministic_result.discrepancy_type}): "
        f"{deterministic_result.explanation}"
    )


def _build_case_context(
    deterministic_result: DeterministicReconciliationResult,
    raw_input: ReconciliationInput,
    tool_context: AgentToolContext,
) -> dict[str, Any]:
    """Build a valid AIReconciliationCaseContext-shaped dict for one invoice.

    Pulls the raw invoice, matched rate card (if any), and dispatch record
    (if any) out of the already-loaded raw_input, plus the normalized
    invoice already computed once per batch in tool_context. This is the
    piece that was previously missing entirely — deterministic_result alone
    does not carry these fields.
    """
    raw_invoice = _find_invoice(raw_input.invoices, deterministic_result.invoice_id)
    matched_rate_card = _find_rate_card(
        raw_input.rate_cards, deterministic_result.matched_rate_id
    )
    dispatch_record = _find_dispatch_record(
        raw_input.dispatch_records, deterministic_result.lr_number
    )
    normalized_invoice = _find_normalized_invoice(
        tool_context, deterministic_result.invoice_id
    )

    evidence_dict = deterministic_result.evidence.model_dump(mode="json")

    return {
        "invoice_data": raw_invoice.model_dump(mode="json") if raw_invoice else {},
        "normalized_invoice_data": (
            normalized_invoice.model_dump(mode="json") if normalized_invoice else None
        ),
        "matched_rate_card": (
            matched_rate_card.model_dump(mode="json") if matched_rate_card else None
        ),
        "dispatch_record": (
            dispatch_record.model_dump(mode="json") if dispatch_record else None
        ),
        "deterministic_checks_performed": deterministic_result.checks_performed,
        "detected_ambiguity": _detected_ambiguity(deterministic_result),
        "calculated_variance": {
            "weight_variance_pct": evidence_dict.get("weight_variance_pct"),
            "acceptable_weight_variance_pct": evidence_dict.get(
                "acceptable_weight_variance_pct"
            ),
        },
        "calculated_financial_impact": {
            "rupee_impact": deterministic_result.rupee_impact,
            "expected_amount": evidence_dict.get("expected_amount"),
        },
        "relevant_evidence": [evidence_dict],
    }


def _resolve_with_ai(
    deterministic_result: DeterministicReconciliationResult,
    raw_input: ReconciliationInput,
    tool_context: AgentToolContext,
) -> MergedInvoiceResult:
    """Call the AI agent for one needs_human invoice and merge the result.

    The AI agent (ai_agent.py) already enforces that any 'flag' decision's
    rupee_impact matches the deterministic value — see
    _validate_result_against_context / _extract_authoritative_rupee_impact
    in ai_agent.py. This function does not re-derive or override rupee_impact;
    it trusts the value ai_agent.py already validated as authoritative.
    """
    case_context = _build_case_context(deterministic_result, raw_input, tool_context)

    raw_result = reconcile_ambiguous_case_with_tools(
        case_context=case_context,
        tool_context=tool_context,
    )

    try:
        ai_result = AIReconciliationResult.model_validate(raw_result)
    except ValidationError as exc:
        # Defensive fallback: ai_agent.py should never emit an invalid shape,
        # but if it ever does, fail safe rather than crash the batch.
        return MergedInvoiceResult(
            invoice_id=deterministic_result.invoice_id,
            lr_number=deterministic_result.lr_number,
            status="needs_human",
            discrepancy_type="ai_result_validation_failed",
            rupee_impact=deterministic_result.rupee_impact,
            matched_rate_id=deterministic_result.matched_rate_id,
            explanation=f"AI agent returned an unparseable result: {exc}",
            resolved_by="ai_agent",
            deterministic_result=deterministic_result,
            ai_result=None,
        )

    return MergedInvoiceResult(
        invoice_id=deterministic_result.invoice_id,
        lr_number=deterministic_result.lr_number,
        status=_map_ai_decision_to_status(ai_result.decision),
        discrepancy_type=ai_result.discrepancy_type,
        rupee_impact=ai_result.rupee_impact,
        matched_rate_id=deterministic_result.matched_rate_id,
        explanation=ai_result.reason,
        resolved_by="ai_agent",
        deterministic_result=deterministic_result,
        ai_result=ai_result.model_dump(mode="json"),
    )


def _keep_deterministic(
    deterministic_result: DeterministicReconciliationResult,
) -> MergedInvoiceResult:
    """Wrap an auto_clear/flagged deterministic result untouched by the AI step."""
    return MergedInvoiceResult(
        invoice_id=deterministic_result.invoice_id,
        lr_number=deterministic_result.lr_number,
        status=deterministic_result.status,
        discrepancy_type=deterministic_result.discrepancy_type,
        rupee_impact=deterministic_result.rupee_impact,
        matched_rate_id=deterministic_result.matched_rate_id,
        explanation=deterministic_result.explanation,
        resolved_by="deterministic",
        deterministic_result=deterministic_result,
        ai_result=None,
    )


def run_reconciliation_batch(batch_id: str) -> BatchResult:
    """Run the full pipeline: ingest -> deterministic pass -> AI pass on
    needs_human invoices only -> merge -> store.
    """
    raw_input = load_reconciliation_input()
    normalized_input = normalize_reconciliation_input(raw_input)

    deterministic_summary = reconcile_input(normalized_input)

    tool_context = AgentToolContext.from_raw_records(
        invoices=raw_input.invoices,
        rate_cards=raw_input.rate_cards,
        dispatch_records=raw_input.dispatch_records,
    )

    merged_results: list[MergedInvoiceResult] = []
    for deterministic_result in deterministic_summary.results:
        if deterministic_result.status == "needs_human":
            merged_results.append(
                _resolve_with_ai(deterministic_result, raw_input, tool_context)
            )
        else:
            merged_results.append(_keep_deterministic(deterministic_result))

    merged_results.sort(key=lambda r: r.invoice_id)

    auto_clear = sum(1 for r in merged_results if r.status == "auto_clear")
    flagged = sum(1 for r in merged_results if r.status == "flagged")
    needs_human = sum(1 for r in merged_results if r.status == "needs_human")

    batch_result = BatchResult(
        batch_id=batch_id,
        total_invoices=len(merged_results),
        auto_clear=auto_clear,
        flagged=flagged,
        needs_human=needs_human,
        results=merged_results,
    )

    _BATCHES[batch_id] = batch_result
    return batch_result


def get_batch_result(batch_id: str) -> BatchResult | None:
    """Retrieve a previously run batch by id, or None if not found."""
    return _BATCHES.get(batch_id)


def get_latest_batch() -> BatchResult | None:
    """Return the most recently stored batch, or None if none have been run."""
    if not _BATCHES:
        return None
    latest_id = next(reversed(_BATCHES))
    return _BATCHES[latest_id]


def reset_batch_store() -> None:
    """Clear the in-memory store. Intended for test isolation only."""
    _BATCHES.clear()