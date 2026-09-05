"""Orchestrate reconciliation across ingestion, matching, and duplicate detection."""

from __future__ import annotations

from models.duplicate import InvoiceDuplicateResult
from models.matching import RateCardMatchResult
from models.normalized import (
    NormalizedDispatchRecord,
    NormalizedInvoice,
    NormalizedRateCardEntry,
    NormalizedReconciliationInput,
)
from models.result import (
    ConfidenceLevel,
    DeterministicReconciliationResult,
    EngineDiscrepancyType,
    ReconciliationEvidence,
    ReconciliationStatus,
    ReconciliationSummary,
)
from services.duplicate_detector import detect_duplicate_lrs
from services.matching import match_invoices_to_rate_cards

MONETARY_TOLERANCE = 0.01


def _round_money(value: float) -> float:
    return round(value, 2)


def _values_match(left: float, right: float, tolerance: float = MONETARY_TOLERANCE) -> bool:
    return abs(_round_money(left) - _round_money(right)) <= tolerance


def _index_dispatch_records(
    dispatch_records: list[NormalizedDispatchRecord],
) -> dict[str, NormalizedDispatchRecord]:
    return {record.lr_number: record for record in dispatch_records}


def _index_duplicate_results(
    duplicate_results: list[InvoiceDuplicateResult],
) -> dict[str, InvoiceDuplicateResult]:
    return {result.invoice_id: result for result in duplicate_results}


def _weight_for_expected_amount(
    invoice: NormalizedInvoice,
    dispatch_record: NormalizedDispatchRecord | None,
) -> float:
    if dispatch_record is not None:
        return dispatch_record.dispatched_weight_tons
    return invoice.weight_billed_tons


def _compute_weight_variance_pct(
    billed_weight: float,
    dispatched_weight: float,
) -> float:
    if dispatched_weight <= 0:
        return 0.0
    return abs(billed_weight - dispatched_weight) / dispatched_weight * 100.0


def _compute_expected_amount(
    weight_tons: float,
    contracted_rate: float,
    contracted_fixed_charge: float,
) -> float:
    return _round_money(weight_tons * contracted_rate + contracted_fixed_charge)


def _compute_rate_impact(
    invoice: NormalizedInvoice,
    contracted_rate: float,
    contracted_fixed_charge: float,
) -> float:
    rate_component = (invoice.rate_applied_per_ton - contracted_rate) * invoice.weight_billed_tons
    fixed_component = invoice.fixed_charge_applied - contracted_fixed_charge
    return _round_money(rate_component + fixed_component)


def _compute_weight_impact(
    billed_weight: float,
    dispatched_weight: float,
    contracted_rate: float,
) -> float:
    return _round_money((billed_weight - dispatched_weight) * contracted_rate)


def _determine_confidence(
    *,
    status: ReconciliationStatus,
    match_result: RateCardMatchResult,
) -> ConfidenceLevel:
    if status == "needs_human":
        return "low"
    if match_result.match_method == "fuzzy":
        return "medium"
    return "high"


def _build_explanation(
    *,
    status: ReconciliationStatus,
    discrepancy_type: EngineDiscrepancyType,
    issues_detected: list[str],
    match_result: RateCardMatchResult,
    duplicate_result: InvoiceDuplicateResult,
) -> str:
    if discrepancy_type == "no_contracted_rate_found":
        return match_result.reason or "No reliable contracted rate card was found for this invoice."

    if discrepancy_type == "none":
        if match_result.match_method == "fuzzy":
            return (
                "Invoice matched a contracted rate card after fuzzy transporter-name "
                "normalization and passed all billing checks."
            )
        return "Invoice matched the contracted rate card and passed all billing checks."

    if discrepancy_type == "duplicate_billing":
        return (
            f"Potential duplicate billing detected for LR {duplicate_result.lr_number}. "
            f"Related invoices: {', '.join(duplicate_result.related_invoice_ids)}."
        )

    if discrepancy_type == "multiple_issues":
        joined = ", ".join(issues_detected)
        return f"Multiple billing issues detected: {joined}."

    if discrepancy_type == "rate_mismatch":
        return (
            "Billed rate or fixed charge differs from the contracted values for the "
            "matched rate card."
        )

    if discrepancy_type == "weight_variance":
        return (
            "Billed weight exceeds the dispatch-record weight beyond the contracted "
            "variance tolerance."
        )

    if status == "needs_human":
        return "Invoice requires human review before a conclusive decision can be made."

    return "Invoice flagged during deterministic reconciliation."


def reconcile_invoice(
    invoice: NormalizedInvoice,
    *,
    match_result: RateCardMatchResult,
    duplicate_result: InvoiceDuplicateResult,
    dispatch_record: NormalizedDispatchRecord | None,
) -> DeterministicReconciliationResult:
    """Run deterministic reconciliation checks for a single invoice."""
    checks_performed: list[str] = ["rate_card_match", "duplicate_lr_check"]
    issues_detected: list[str] = []

    evidence = ReconciliationEvidence(
        match_status=match_result.match_status,
        match_method=match_result.match_method,
        similarity_score=match_result.similarity_score,
        billed_rate_per_ton=invoice.rate_applied_per_ton,
        billed_fixed_charge=invoice.fixed_charge_applied,
        billed_weight_tons=invoice.weight_billed_tons,
        billed_amount=invoice.total_amount,
        duplicate_related_invoice_ids=list(duplicate_result.related_invoice_ids),
        duplicate_reason=duplicate_result.reason,
        match_reason=match_result.reason,
    )

    is_duplicate = duplicate_result.duplicate_status == "potential_duplicate"
    if is_duplicate:
        issues_detected.append("duplicate_billing")

    if match_result.match_status != "matched" or not match_result.is_reliable:
        checks_performed.append("contract_lookup")
        result = DeterministicReconciliationResult(
            invoice_id=invoice.raw.invoice_id,
            lr_number=invoice.lr_number,
            status="needs_human",
            discrepancy_type="no_contracted_rate_found",
            rupee_impact=0.0,
            matched_rate_id=None,
            checks_performed=checks_performed,
            explanation=_build_explanation(
                status="needs_human",
                discrepancy_type="no_contracted_rate_found",
                issues_detected=issues_detected,
                match_result=match_result,
                duplicate_result=duplicate_result,
            ),
            confidence="low",
            evidence=evidence.model_copy(update={"issues_detected": issues_detected}),
        )
        return result

    rate_card = match_result.matched_rate_card
    assert rate_card is not None

    evidence.contracted_rate_per_ton = rate_card.rate_per_ton
    evidence.contracted_fixed_charge = rate_card.fixed_charge
    evidence.acceptable_weight_variance_pct = rate_card.acceptable_weight_variance_pct

    checks_performed.extend(["rate_comparison", "expected_amount_calculation"])

    rate_mismatch = not _values_match(
        invoice.rate_applied_per_ton,
        rate_card.rate_per_ton,
    ) or not _values_match(invoice.fixed_charge_applied, rate_card.fixed_charge)
    if rate_mismatch:
        issues_detected.append("rate_mismatch")
        evidence.rate_impact = _compute_rate_impact(
            invoice,
            rate_card.rate_per_ton,
            rate_card.fixed_charge,
        )

    weight_for_expected_amount = _weight_for_expected_amount(invoice, dispatch_record)
    evidence.weight_for_expected_amount_tons = weight_for_expected_amount
    evidence.expected_amount = _compute_expected_amount(
        weight_for_expected_amount,
        rate_card.rate_per_ton,
        rate_card.fixed_charge,
    )

    weight_variance_excess = False
    if dispatch_record is not None:
        checks_performed.append("weight_variance_check")
        evidence.dispatched_weight_tons = dispatch_record.dispatched_weight_tons
        variance_pct = _compute_weight_variance_pct(
            invoice.weight_billed_tons,
            dispatch_record.dispatched_weight_tons,
        )
        evidence.weight_variance_pct = _round_money(variance_pct)
        if variance_pct > rate_card.acceptable_weight_variance_pct:
            weight_variance_excess = True
            issues_detected.append("weight_variance")
            evidence.weight_impact = _compute_weight_impact(
                invoice.weight_billed_tons,
                dispatch_record.dispatched_weight_tons,
                rate_card.rate_per_ton,
            )

    contractual_impact = 0.0
    if evidence.expected_amount is not None:
        contractual_impact = _round_money(invoice.total_amount - evidence.expected_amount)

    if is_duplicate:
        rupee_impact = _round_money(invoice.total_amount)
    elif issues_detected:
        rupee_impact = contractual_impact
    else:
        rupee_impact = 0.0

    if len(issues_detected) > 1:
        discrepancy_type: EngineDiscrepancyType = "multiple_issues"
        status: ReconciliationStatus = "flagged"
    elif is_duplicate:
        discrepancy_type = "duplicate_billing"
        status = "flagged"
    elif rate_mismatch:
        discrepancy_type = "rate_mismatch"
        status = "flagged"
    elif weight_variance_excess:
        discrepancy_type = "weight_variance"
        status = "flagged"
    else:
        discrepancy_type = "none"
        status = "auto_clear"

    evidence.issues_detected = issues_detected
    confidence = _determine_confidence(status=status, match_result=match_result)

    return DeterministicReconciliationResult(
        invoice_id=invoice.raw.invoice_id,
        lr_number=invoice.lr_number,
        status=status,
        discrepancy_type=discrepancy_type,
        rupee_impact=rupee_impact,
        matched_rate_id=rate_card.raw.rate_id,
        checks_performed=checks_performed,
        explanation=_build_explanation(
            status=status,
            discrepancy_type=discrepancy_type,
            issues_detected=issues_detected,
            match_result=match_result,
            duplicate_result=duplicate_result,
        ),
        confidence=confidence,
        evidence=evidence,
    )


def reconcile_invoices(
    invoices: list[NormalizedInvoice],
    rate_cards: list[NormalizedRateCardEntry],
    dispatch_records: list[NormalizedDispatchRecord],
) -> list[DeterministicReconciliationResult]:
    """Reconcile all invoices against rate cards, dispatch records, and duplicate checks."""
    dispatch_by_lr = _index_dispatch_records(dispatch_records)
    duplicate_by_invoice = _index_duplicate_results(
        detect_duplicate_lrs(invoices).invoice_results
    )
    match_results = {
        result.invoice_id: result
        for result in match_invoices_to_rate_cards(invoices, rate_cards)
    }

    results: list[DeterministicReconciliationResult] = []
    for invoice in invoices:
        invoice_id = invoice.raw.invoice_id
        match_result = match_results[invoice_id]
        duplicate_result = duplicate_by_invoice[invoice_id]
        dispatch_record = dispatch_by_lr.get(invoice.lr_number)

        results.append(
            reconcile_invoice(
                invoice,
                match_result=match_result,
                duplicate_result=duplicate_result,
                dispatch_record=dispatch_record,
            )
        )

    results.sort(key=lambda result: result.invoice_id)
    return results


def reconcile_input(
    data: NormalizedReconciliationInput,
) -> ReconciliationSummary:
    """Run deterministic reconciliation for a normalized input bundle."""
    results = reconcile_invoices(
        data.invoices,
        data.rate_cards,
        data.dispatch_records,
    )
    return ReconciliationSummary(
        total_invoices=len(results),
        auto_clear=sum(1 for result in results if result.status == "auto_clear"),
        flagged=sum(1 for result in results if result.status == "flagged"),
        needs_human=sum(1 for result in results if result.status == "needs_human"),
        results=results,
    )
