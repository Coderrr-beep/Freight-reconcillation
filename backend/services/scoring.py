    
"""
Score a completed reconciliation batch against ground truth labels.

This is the ONLY module in the codebase permitted to read data/invoices.json
(the ground truth answer key). It must never be imported by ingestion.py,
matching.py, reconciliation.py, ai_agent.py, agent_tools.py, or
orchestrator.py — none of those modules should ever see ground truth.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from models.result import (
    BatchResult,
    GroundTruth,
    ScoredInvoiceResult,
    ScoringReport,
)

# Mirrors DEFAULT_DATA_DIR in ingestion.py: backend/services/../../.. -> project root -> data/
DEFAULT_GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "invoices.json"
)


class ScoringError(Exception):
    """Raised when ground truth cannot be loaded or matched to a batch result."""


def _load_ground_truth(path: Path | None = None) -> dict[str, GroundTruth]:
    gt_path = path or DEFAULT_GROUND_TRUTH_PATH
    if not gt_path.exists():
        raise ScoringError(f"Ground truth file not found at {gt_path}")

    try:
        raw = json.loads(gt_path.read_text())
    except json.JSONDecodeError as exc:
        raise ScoringError(f"Ground truth file is not valid JSON: {exc}") from exc

    ground_truth: dict[str, GroundTruth] = {}
    for record in raw:
        invoice_id = record.get("invoice_id")
        gt_block = record.get("ground_truth")
        if invoice_id is None or gt_block is None:
            raise ScoringError(
                f"Ground truth record missing invoice_id or ground_truth block: {record}"
            )
        try:
            ground_truth[invoice_id] = GroundTruth.model_validate(gt_block)
        except ValidationError as exc:
            raise ScoringError(f"Invalid ground_truth for {invoice_id}: {exc}") from exc

    return ground_truth


def score_batch(
    batch_result: BatchResult, ground_truth_path: Path | None = None
) -> ScoringReport:
    """Compare a batch's final decisions against ground truth and compute metrics."""
    ground_truth = _load_ground_truth(ground_truth_path)

    tp = fp = tn = fn = 0
    correctly_routed_to_exception = 0
    incorrectly_force_resolved = 0
    unresolved_resolvable_case = 0

    false_positive_cost = 0.0
    total_rupee_impact_caught = 0.0

    breakdown: list[ScoredInvoiceResult] = []

    for result in batch_result.results:
        gt = ground_truth.get(result.invoice_id)
        if gt is None:
            raise ScoringError(f"No ground truth found for invoice_id {result.invoice_id}")

        if gt.is_discrepancy is None:
            # Genuinely ambiguous case (e.g. no_contracted_rate_found) —
            # there is no knowable correct clear/flag answer, so the only
            # correct system behavior is to route it to a human.
            if result.status == "needs_human":
                classification = "correctly_routed_to_exception"
                correctly_routed_to_exception += 1
                correct = True
            else:
                classification = "incorrectly_force_resolved"
                incorrectly_force_resolved += 1
                correct = False
        else:
            actual_positive = gt.is_discrepancy is True
            if result.status == "flagged":
                if actual_positive:
                    classification = "true_positive"
                    tp += 1
                    correct = True
                    total_rupee_impact_caught += gt.rupee_impact or 0.0
                else:
                    classification = "false_positive"
                    fp += 1
                    correct = False
                    # Cost = what the SYSTEM claimed, not ground truth (which
                    # is 0 for a wrongly-flagged clean invoice by definition)
                    # — this represents wasted human investigation time.
                    false_positive_cost += result.rupee_impact or 0.0
            elif result.status == "auto_clear":
                if actual_positive:
                    classification = "false_negative"
                    fn += 1
                    correct = False
                else:
                    classification = "true_negative"
                    tn += 1
                    correct = True
            else:
                # needs_human on a case that DID have a definite ground truth
                # answer — should not occur given the current deterministic
                # engine + AI agent design (see conversation notes), but
                # handled explicitly rather than silently mis-bucketed.
                classification = "unresolved_resolvable_case"
                unresolved_resolvable_case += 1
                correct = False

        breakdown.append(
            ScoredInvoiceResult(
                invoice_id=result.invoice_id,
                predicted_status=result.status,
                actual_is_discrepancy=gt.is_discrepancy,
                actual_type=gt.type,
                classification=classification,
                correct=correct,
            )
        )

    total_scoreable = tp + fp + tn + fn
    precision = (tp / (tp + fp)) if (tp + fp) > 0 else None
    recall = (tp / (tp + fn)) if (tp + fn) > 0 else None
    match_rate = ((tp + tn) / total_scoreable) if total_scoreable > 0 else None

    return ScoringReport(
        batch_id=batch_result.batch_id,
        total_invoices=len(batch_result.results),
        total_scoreable_invoices=total_scoreable,
        true_positive=tp,
        false_positive=fp,
        true_negative=tn,
        false_negative=fn,
        correctly_routed_to_exception=correctly_routed_to_exception,
        incorrectly_force_resolved=incorrectly_force_resolved,
        unresolved_resolvable_case=unresolved_resolvable_case,
        precision=precision,
        recall=recall,
        match_rate=match_rate,
        false_positive_cost_rupees=round(false_positive_cost, 2),
        total_rupee_impact_correctly_caught=round(total_rupee_impact_caught, 2),
        breakdown=breakdown,
    )