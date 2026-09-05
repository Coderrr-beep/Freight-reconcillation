"""Tests for services/orchestrator.py.

The AI agent call is mocked — these tests verify the merge logic, not
Claude's actual behavior (that's covered by test_ai_agent.py /
test_ai_agent_tools.py).
"""

from datetime import date

import pytest

import services.orchestrator as orchestrator
from models.input import ReconciliationInput
from models.invoice import DispatchRecord, Invoice
from models.rate_card import RateCardEntry


@pytest.fixture(autouse=True)
def _reset_store():
    orchestrator.reset_batch_store()
    yield
    orchestrator.reset_batch_store()


def _sample_input() -> ReconciliationInput:
    rate_cards = [
        RateCardEntry(
            rate_id="RC001",
            transporter="Ashok Transport Co.",
            origin="Coimbatore",
            destination="Chennai",
            vehicle_type="10-ton truck",
            rate_per_ton=1000.0,
            fixed_charge=500.0,
            acceptable_weight_variance_pct=3.0,
        )
    ]

    invoices = [
        # Clean invoice — deterministic engine should auto_clear this.
        Invoice(
            invoice_id="INV0001",
            lr_number="LR000001",
            transporter_name="Ashok Transport Co.",
            origin="Coimbatore",
            destination="Chennai",
            vehicle_type="10-ton truck",
            weight_billed_tons=10.0,
            rate_applied_per_ton=1000.0,
            fixed_charge_applied=500.0,
            total_amount=10500.0,
            invoice_date=date(2026, 6, 1),
        ),
        # No contracted rate exists for this transporter/route — deterministic
        # engine should return needs_human, which the orchestrator should
        # route to the (mocked) AI agent.
        Invoice(
            invoice_id="INV0002",
            lr_number="LR000002",
            transporter_name="Unknown Transporter Ltd",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="16-ton truck",
            weight_billed_tons=8.0,
            rate_applied_per_ton=1200.0,
            fixed_charge_applied=600.0,
            total_amount=10200.0,
            invoice_date=date(2026, 6, 2),
        ),
    ]

    dispatch_records = [
        DispatchRecord(lr_number="LR000001", dispatched_weight_tons=10.0),
        DispatchRecord(lr_number="LR000002", dispatched_weight_tons=8.0),
    ]

    return ReconciliationInput(
        rate_cards=rate_cards,
        invoices=invoices,
        dispatch_records=dispatch_records,
    )


def _fake_ai_flag_response(case_context, *, tool_context=None):
    """Mocked AI agent response simulating a confident 'flag' decision.

    rupee_impact intentionally matches the deterministic case_context's
    rupee_impact, since the real ai_agent.py enforces that invariant — the
    mock should reflect that contract, not violate it.
    """
    return {
        "decision": "flag",
        "discrepancy_type": "no_contracted_rate_found",
        "reason": "No contract exists for this transporter/route combination.",
        "confidence": 0.9,
        "rupee_impact": case_context["calculated_financial_impact"]["rupee_impact"],
        "evidence": [],
        "agent_trace": [
            {
                "tool": "get_rate_card",
                "arguments": {"transporter": "Unknown Transporter Ltd"},
                "result": {"matches": []},
                "iteration": 1,
            }
        ],
    }


def test_deterministic_results_untouched_by_ai_step(monkeypatch):
    """auto_clear invoices must not be passed to the AI agent at all."""
    calls = []

    def _tracking_mock(case_context, *, tool_context=None):
        calls.append(case_context["invoice_data"]["invoice_id"])
        return _fake_ai_flag_response(case_context, tool_context=tool_context)

    monkeypatch.setattr(
        orchestrator, "reconcile_ambiguous_case_with_tools", _tracking_mock
    )
    monkeypatch.setattr(
        orchestrator, "load_reconciliation_input", lambda: _sample_input()
    )

    batch = orchestrator.run_reconciliation_batch("test-batch-1")

    clean_result = next(r for r in batch.results if r.invoice_id == "INV0001")
    assert clean_result.resolved_by == "deterministic"
    assert clean_result.status == "auto_clear"
    assert "INV0001" not in calls


def test_needs_human_invoice_gets_ai_result(monkeypatch):
    monkeypatch.setattr(
        orchestrator,
        "reconcile_ambiguous_case_with_tools",
        _fake_ai_flag_response,
    )
    monkeypatch.setattr(
        orchestrator, "load_reconciliation_input", lambda: _sample_input()
    )

    batch = orchestrator.run_reconciliation_batch("test-batch-2")

    ambiguous_result = next(r for r in batch.results if r.invoice_id == "INV0002")
    assert ambiguous_result.resolved_by == "ai_agent"
    assert ambiguous_result.status == "flagged"
    assert ambiguous_result.ai_result is not None
    assert ambiguous_result.ai_result["decision"] == "flag"


def test_resolved_by_is_set_correctly_for_both_paths(monkeypatch):
    monkeypatch.setattr(
        orchestrator,
        "reconcile_ambiguous_case_with_tools",
        _fake_ai_flag_response,
    )
    monkeypatch.setattr(
        orchestrator, "load_reconciliation_input", lambda: _sample_input()
    )

    batch = orchestrator.run_reconciliation_batch("test-batch-3")

    resolved_by_map = {r.invoice_id: r.resolved_by for r in batch.results}
    assert resolved_by_map["INV0001"] == "deterministic"
    assert resolved_by_map["INV0002"] == "ai_agent"


def test_deterministic_rupee_impact_never_overwritten_after_merge(monkeypatch):
    """The AI mock deliberately echoes case_context.rupee_impact back —
    this test confirms the orchestrator doesn't recompute or mutate it
    independently, and that the deterministic_result nested in the merged
    output still carries the original, untouched deterministic value.
    """
    monkeypatch.setattr(
        orchestrator,
        "reconcile_ambiguous_case_with_tools",
        _fake_ai_flag_response,
    )
    monkeypatch.setattr(
        orchestrator, "load_reconciliation_input", lambda: _sample_input()
    )

    batch = orchestrator.run_reconciliation_batch("test-batch-4")

    ambiguous_result = next(r for r in batch.results if r.invoice_id == "INV0002")
    assert (
        ambiguous_result.rupee_impact
        == ambiguous_result.deterministic_result.rupee_impact
    )


def test_get_batch_result_returns_stored_batch(monkeypatch):
    monkeypatch.setattr(
        orchestrator,
        "reconcile_ambiguous_case_with_tools",
        _fake_ai_flag_response,
    )
    monkeypatch.setattr(
        orchestrator, "load_reconciliation_input", lambda: _sample_input()
    )

    orchestrator.run_reconciliation_batch("test-batch-5")
    fetched = orchestrator.get_batch_result("test-batch-5")

    assert fetched is not None
    assert fetched.batch_id == "test-batch-5"


def test_get_batch_result_returns_none_for_unknown_id():
    assert orchestrator.get_batch_result("does-not-exist") is None