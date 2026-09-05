"""Tests for services/scoring.py using hand-built batch results and a
temporary ground truth fixture — does not touch the real data/invoices.json.
"""

import json

import pytest

from models.result import (
    BatchResult,
    DeterministicReconciliationResult,
    MergedInvoiceResult,
    ReconciliationEvidence,
)
from services.scoring import ScoringError, score_batch


def _det_result(invoice_id, status, discrepancy_type="none", rupee_impact=0.0):
    return DeterministicReconciliationResult(
        invoice_id=invoice_id,
        lr_number=f"LR-{invoice_id}",
        status=status,
        discrepancy_type=discrepancy_type,
        rupee_impact=rupee_impact,
        matched_rate_id=None,
        checks_performed=["rate_card_match"],
        explanation="test fixture",
        confidence="high",
        evidence=ReconciliationEvidence(),
    )


def _merged(invoice_id, status, discrepancy_type="none", rupee_impact=0.0, resolved_by="deterministic"):
    det = _det_result(invoice_id, status, discrepancy_type, rupee_impact)
    return MergedInvoiceResult(
        invoice_id=invoice_id,
        lr_number=det.lr_number,
        status=status,
        discrepancy_type=discrepancy_type,
        rupee_impact=rupee_impact,
        matched_rate_id=None,
        explanation="test fixture",
        resolved_by=resolved_by,
        deterministic_result=det,
        ai_result=None,
    )


def _write_ground_truth(tmp_path, records):
    path = tmp_path / "invoices.json"
    path.write_text(json.dumps(records))
    return path


def test_perfect_predictions_score_1_0_precision_and_recall(tmp_path):
    results = [
        _merged("INV0001", "auto_clear"),
        _merged("INV0002", "flagged", "rate_mismatch", 500.0),
    ]
    gt = [
        {
            "invoice_id": "INV0001",
            "ground_truth": {
                "is_discrepancy": False,
                "type": "clean",
                "expected_action": "auto_clear",
                "rupee_impact": 0.0,
            },
        },
        {
            "invoice_id": "INV0002",
            "ground_truth": {
                "is_discrepancy": True,
                "type": "rate_mismatch",
                "expected_action": "flag",
                "rupee_impact": 500.0,
            },
        },
    ]
    gt_path = _write_ground_truth(tmp_path, gt)
    batch = BatchResult(
        batch_id="b1", total_invoices=2, auto_clear=1, flagged=1, needs_human=0, results=results
    )

    report = score_batch(batch, ground_truth_path=gt_path)

    assert report.precision == 1.0
    assert report.recall == 1.0
    assert report.true_positive == 1
    assert report.true_negative == 1
    assert report.false_positive == 0
    assert report.false_negative == 0
    assert report.total_rupee_impact_correctly_caught == 500.0


def test_one_false_positive(tmp_path):
    results = [_merged("INV0001", "flagged", "rate_mismatch", 300.0)]
    gt = [
        {
            "invoice_id": "INV0001",
            "ground_truth": {
                "is_discrepancy": False,
                "type": "clean",
                "expected_action": "auto_clear",
                "rupee_impact": 0.0,
            },
        }
    ]
    gt_path = _write_ground_truth(tmp_path, gt)
    batch = BatchResult(
        batch_id="b2", total_invoices=1, auto_clear=0, flagged=1, needs_human=0, results=results
    )

    report = score_batch(batch, ground_truth_path=gt_path)

    assert report.false_positive == 1
    assert report.precision == 0.0
    assert report.recall is None  # no actual positives exist, recall undefined
    assert report.false_positive_cost_rupees == 300.0


def test_one_false_negative(tmp_path):
    results = [_merged("INV0001", "auto_clear")]
    gt = [
        {
            "invoice_id": "INV0001",
            "ground_truth": {
                "is_discrepancy": True,
                "type": "rate_mismatch",
                "expected_action": "flag",
                "rupee_impact": 750.0,
            },
        }
    ]
    gt_path = _write_ground_truth(tmp_path, gt)
    batch = BatchResult(
        batch_id="b3", total_invoices=1, auto_clear=1, flagged=0, needs_human=0, results=results
    )

    report = score_batch(batch, ground_truth_path=gt_path)

    assert report.false_negative == 1
    assert report.recall == 0.0
    assert report.total_rupee_impact_correctly_caught == 0.0


def test_null_ground_truth_case_correctly_routed_to_exception(tmp_path):
    results = [
        _merged("INV0001", "needs_human", "no_contracted_rate_found", resolved_by="ai_agent")
    ]
    gt = [
        {
            "invoice_id": "INV0001",
            "ground_truth": {
                "is_discrepancy": None,
                "type": "no_contracted_rate_found",
                "expected_action": "needs_human",
                "rupee_impact": None,
            },
        }
    ]
    gt_path = _write_ground_truth(tmp_path, gt)
    batch = BatchResult(
        batch_id="b4", total_invoices=1, auto_clear=0, flagged=0, needs_human=1, results=results
    )

    report = score_batch(batch, ground_truth_path=gt_path)

    assert report.correctly_routed_to_exception == 1
    assert report.total_scoreable_invoices == 0  # excluded from precision/recall
    assert report.precision is None
    assert report.breakdown[0].classification == "correctly_routed_to_exception"
    assert report.breakdown[0].correct is True


def test_null_ground_truth_case_wrongly_force_resolved(tmp_path):
    results = [
        _merged("INV0001", "flagged", "no_contracted_rate_found", 1200.0, resolved_by="ai_agent")
    ]
    gt = [
        {
            "invoice_id": "INV0001",
            "ground_truth": {
                "is_discrepancy": None,
                "type": "no_contracted_rate_found",
                "expected_action": "needs_human",
                "rupee_impact": None,
            },
        }
    ]
    gt_path = _write_ground_truth(tmp_path, gt)
    batch = BatchResult(
        batch_id="b5", total_invoices=1, auto_clear=0, flagged=1, needs_human=0, results=results
    )

    report = score_batch(batch, ground_truth_path=gt_path)

    assert report.incorrectly_force_resolved == 1
    assert report.breakdown[0].classification == "incorrectly_force_resolved"
    assert report.breakdown[0].correct is False


def test_missing_ground_truth_file_raises_scoring_error(tmp_path):
    results = [_merged("INV0001", "auto_clear")]
    batch = BatchResult(
        batch_id="b6", total_invoices=1, auto_clear=1, flagged=0, needs_human=0, results=results
    )

    with pytest.raises(ScoringError):
        score_batch(batch, ground_truth_path=tmp_path / "does_not_exist.json")


def test_invoice_missing_from_ground_truth_raises_scoring_error(tmp_path):
    results = [_merged("INV9999", "auto_clear")]
    gt_path = _write_ground_truth(tmp_path, [])
    batch = BatchResult(
        batch_id="b7", total_invoices=1, auto_clear=1, flagged=0, needs_human=0, results=results
    )

    with pytest.raises(ScoringError):
        score_batch(batch, ground_truth_path=gt_path)