from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from services.ingestion import (
    DISPATCH_FILENAME,
    INVOICES_FILENAME,
    RATE_CARD_FILENAME,
    load_reconciliation_input,
)
from services.normalization import normalize_reconciliation_input
from services.reconciliation import reconcile_input


EXPECTED_SUMMARY = {
    "total_invoices": 90,
    "auto_clear": 63,
    "flagged": 22,
    "needs_human": 5,
    "rate_mismatch": 14,
    "weight_variance": 4,
    "duplicate": 4,
    "no_contract": 5,
    "total_rupee_impact": 113293.24,
}

REPRESENTATIVE_TYPES = (
    "none",
    "rate_mismatch",
    "weight_variance",
    "duplicate_billing",
    "no_contracted_rate_found",
)


def _result_summary(results: list[object]) -> dict[str, float | int]:
    discrepancy_counts = Counter(result.discrepancy_type for result in results)
    issue_counts = Counter(
        issue
        for result in results
        for issue in result.evidence.issues_detected
    )

    return {
        "rate_mismatch": issue_counts["rate_mismatch"],
        "weight_variance": issue_counts["weight_variance"],
        "duplicate": issue_counts["duplicate_billing"],
        "no_contract": discrepancy_counts["no_contracted_rate_found"],
        "total_rupee_impact": round(
            sum(result.rupee_impact for result in results),
            2,
        ),
    }


def _representative_results(results: list[object]) -> list[object]:
    representatives: list[object] = []
    for discrepancy_type in REPRESENTATIVE_TYPES:
        matching_results = [
            result
            for result in results
            if result.discrepancy_type == discrepancy_type
        ]
        representatives.extend(matching_results[:2])

    return representatives[:10]


def _print_reconciliation_report(summary: object, aggregate_counts: dict[str, float | int]) -> None:
    print("\nEND-TO-END DETERMINISTIC RECONCILIATION SUMMARY")
    print(f"total invoices: {summary.total_invoices}")
    print(f"auto_clear count: {summary.auto_clear}")
    print(f"flagged count: {summary.flagged}")
    print(f"needs_human count: {summary.needs_human}")
    print(f"rate mismatch count: {aggregate_counts['rate_mismatch']}")
    print(f"weight variance count: {aggregate_counts['weight_variance']}")
    print(f"duplicate count: {aggregate_counts['duplicate']}")
    print(f"no contract count: {aggregate_counts['no_contract']}")
    print(f"total ₹ impact: ₹{aggregate_counts['total_rupee_impact']:,.2f}")

    print("\nREPRESENTATIVE RECONCILIATION RESULTS")
    for result in _representative_results(summary.results):
        matched_rate_id = result.matched_rate_id or "-"
        print(
            f"{result.invoice_id} | "
            f"status={result.status} | "
            f"discrepancy_type={result.discrepancy_type} | "
            f"₹ impact=₹{result.rupee_impact:,.2f} | "
            f"reason={result.explanation} | "
            f"matched_rate_id={matched_rate_id}"
        )


def test_engine_reconciles_synthetic_inputs_end_to_end(monkeypatch: Any) -> None:
    loaded_file_names: list[str] = []
    original_read_text = Path.read_text

    def guarded_read_text(path: Path, *args: Any, **kwargs: Any) -> str:
        loaded_file_names.append(path.name)
        if path.name == "invoices.json":
            raise AssertionError(
                "End-to-end reconciliation must not read invoices.json or "
                "ground_truth labels."
            )
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    raw_input = load_reconciliation_input()
    normalized_input = normalize_reconciliation_input(raw_input)
    summary = reconcile_input(normalized_input)

    aggregate_counts = {
        "total_invoices": summary.total_invoices,
        "auto_clear": summary.auto_clear,
        "flagged": summary.flagged,
        "needs_human": summary.needs_human,
        **_result_summary(summary.results),
    }

    _print_reconciliation_report(summary, aggregate_counts)

    assert loaded_file_names == [
        RATE_CARD_FILENAME,
        INVOICES_FILENAME,
        DISPATCH_FILENAME,
    ]
    assert len(summary.results) == len(raw_input.invoices)
    assert len(summary.results) == summary.total_invoices
    assert len(_representative_results(summary.results)) == 10
    assert aggregate_counts == EXPECTED_SUMMARY
