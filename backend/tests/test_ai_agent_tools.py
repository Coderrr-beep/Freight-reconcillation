from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest

from models.invoice import DispatchRecord, Invoice
from models.rate_card import RateCardEntry
from services import ai_agent
from services.agent_tools import AgentToolContext
from services.ai_agent import ClaudeAPIError, reconcile_ambiguous_case_with_tools


@pytest.fixture
def tool_context() -> AgentToolContext:
    invoices = [
        Invoice(
            invoice_id="INV001",
            lr_number="LR100001",
            transporter_name="Bharat Roadlines",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="20-ton trailer",
            weight_billed_tons=10.0,
            rate_applied_per_ton=1000.0,
            fixed_charge_applied=500.0,
            total_amount=10500.0,
            invoice_date=date(2026, 6, 1),
        ),
    ]
    rate_cards = [
        RateCardEntry(
            rate_id="RC001",
            transporter="Bharat Roadlines",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="20-ton trailer",
            rate_per_ton=1000.0,
            fixed_charge=500.0,
            acceptable_weight_variance_pct=3.0,
        ),
    ]
    dispatch_records = [
        DispatchRecord(lr_number="LR100001", dispatched_weight_tons=10.0),
    ]
    return AgentToolContext.from_raw_records(
        invoices=invoices,
        rate_cards=rate_cards,
        dispatch_records=dispatch_records,
    )


def _case_context(*, include_impact: bool = False) -> dict[str, Any]:
    context: dict[str, Any] = {
        "invoice_data": {
            "invoice_id": "INV001",
            "lr_number": "LR100001",
            "transporter_name": "Bharat Roadlines",
            "origin": "Pune",
            "destination": "Mumbai",
            "vehicle_type": "20-ton trailer",
            "weight_billed_tons": 10.0,
            "total_amount": 11500.0,
        },
        "normalized_invoice_data": {
            "invoice_id": "INV001",
            "lr_number": "LR100001",
            "transporter_name": "Bharat Roadlines",
            "origin": "Pune",
            "destination": "Mumbai",
            "vehicle_type": "20-ton trailer",
            "weight_billed_tons": 10.0,
            "total_amount": 11500.0,
        },
        "matched_rate_card": None,
        "dispatch_record": None,
        "deterministic_checks_performed": ["rate_card_match"],
        "detected_ambiguity": "Rate-card match was ambiguous and needs investigation.",
        "calculated_variance": None,
        "calculated_financial_impact": None,
        "relevant_evidence": [
            {
                "source": "invoice",
                "field": "invoice_id",
                "value": "INV001",
            }
        ],
    }
    if include_impact:
        context["calculated_financial_impact"] = {"rupee_impact": 1000.0}
    return context


def _tool_use(name: str, tool_input: dict[str, Any], tool_use_id: str = "toolu_1") -> dict[str, Any]:
    return {
        "stop_reason": "tool_use",
        "content": [
            {
                "type": "tool_use",
                "id": tool_use_id,
                "name": name,
                "input": tool_input,
            }
        ],
    }


def _multi_tool_use(*blocks: dict[str, Any]) -> dict[str, Any]:
    return {
        "stop_reason": "tool_use",
        "content": [
            {"type": "tool_use", **block}
            for block in blocks
        ],
    }


def _final(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": json.dumps(payload)}],
    }


def _decision(
    *,
    decision: str = "needs_human",
    discrepancy_type: str = "insufficient_evidence",
    reason: str = "The supplied evidence is insufficient.",
    confidence: float = 0.0,
    rupee_impact: float = 0.0,
    evidence: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "decision": decision,
        "discrepancy_type": discrepancy_type,
        "reason": reason,
        "confidence": confidence,
        "rupee_impact": rupee_impact,
        "evidence": evidence or [],
        "agent_trace": [],
    }


def _mock_claude(monkeypatch: Any, responses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_post_to_claude(
        payload: dict[str, Any],
        *,
        api_key: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        calls.append(payload)
        assert api_key == "test-claude-key"
        assert timeout_seconds == 10.0
        return responses.pop(0)

    monkeypatch.setenv("CLAUDE_API_KEY", "test-claude-key")
    monkeypatch.setattr(ai_agent, "_post_to_claude", fake_post_to_claude)
    return calls


def test_claude_requests_get_rate_card(
    monkeypatch: Any,
    tool_context: AgentToolContext,
) -> None:
    calls = _mock_claude(
        monkeypatch,
        [
            _tool_use(
                "get_rate_card",
                {
                    "transporter": "Bharat Roadlines",
                    "origin": "Pune",
                    "destination": "Mumbai",
                    "vehicle_type": "20-ton trailer",
                },
            ),
            _final(
                _decision(
                    decision="clear",
                    discrepancy_type="none",
                    reason="The retrieved contract supports the invoice route.",
                    confidence=0.78,
                    evidence=[
                        {
                            "source": "rate_card",
                            "field": "rate_id",
                            "value": "RC001",
                        }
                    ],
                )
            ),
        ],
    )

    result = reconcile_ambiguous_case_with_tools(
        _case_context(),
        tool_context=tool_context,
    )

    assert result["decision"] == "clear"
    assert result["rupee_impact"] == 0.0
    assert result["agent_trace"][0]["tool"] == "get_rate_card"
    assert result["agent_trace"][0]["result"]["contracts"][0]["rate_id"] == "RC001"
    assert calls[0]["tools"]


def test_claude_requests_dispatch_record(
    monkeypatch: Any,
    tool_context: AgentToolContext,
) -> None:
    _mock_claude(
        monkeypatch,
        [
            _tool_use("get_dispatch_record", {"lr_number": "LR100001"}),
            _final(
                _decision(
                    decision="clear",
                    discrepancy_type="none",
                    reason="The dispatch record confirms the shipment LR.",
                    confidence=0.74,
                    evidence=[
                        {
                            "source": "dispatch",
                            "field": "dispatched_weight_tons",
                            "value": "10.0",
                        }
                    ],
                )
            ),
        ],
    )

    result = reconcile_ambiguous_case_with_tools(
        _case_context(),
        tool_context=tool_context,
    )

    assert result["decision"] == "clear"
    assert result["agent_trace"][0]["tool"] == "get_dispatch_record"


def test_multiple_tool_calls_work_in_one_iteration(
    monkeypatch: Any,
    tool_context: AgentToolContext,
) -> None:
    _mock_claude(
        monkeypatch,
        [
            _multi_tool_use(
                {
                    "id": "toolu_dispatch",
                    "name": "get_dispatch_record",
                    "input": {"lr_number": "LR100001"},
                },
                {
                    "id": "toolu_variance",
                    "name": "calculate_weight_variance",
                    "input": {
                        "billed_weight": 11.0,
                        "dispatched_weight": 10.0,
                        "tolerance": 3.0,
                    },
                },
            ),
            _final(
                _decision(
                    decision="flag",
                    discrepancy_type="weight_variance",
                    reason="The deterministic tool says variance exceeds tolerance.",
                    confidence=0.9,
                    rupee_impact=0.0,
                    evidence=[
                        {
                            "source": "dispatch",
                            "field": "variance_percent",
                            "value": "10.0",
                        }
                    ],
                )
            ),
        ],
    )

    result = reconcile_ambiguous_case_with_tools(
        _case_context(),
        tool_context=tool_context,
    )

    assert result["decision"] == "flag"
    assert [entry["tool"] for entry in result["agent_trace"]] == [
        "get_dispatch_record",
        "calculate_weight_variance",
    ]
    assert {entry["iteration"] for entry in result["agent_trace"]} == {1}


def test_unknown_tool_is_rejected(monkeypatch: Any, tool_context: AgentToolContext) -> None:
    _mock_claude(
        monkeypatch,
        [_tool_use("read_file", {"path": "data/rate_card.json"})],
    )

    result = reconcile_ambiguous_case_with_tools(
        _case_context(include_impact=True),
        tool_context=tool_context,
    )

    assert result["decision"] == "needs_human"
    assert result["discrepancy_type"] == "ai_tool_failure"
    assert result["rupee_impact"] == 1000.0
    assert result["agent_trace"][0]["tool"] == "read_file"
    assert "Unknown tool" in result["agent_trace"][0]["result"]["error"]


def test_invalid_tool_arguments_are_rejected(
    monkeypatch: Any,
    tool_context: AgentToolContext,
) -> None:
    _mock_claude(
        monkeypatch,
        [_tool_use("get_rate_card", {"transporter": "Bharat Roadlines"})],
    )

    result = reconcile_ambiguous_case_with_tools(
        _case_context(include_impact=True),
        tool_context=tool_context,
    )

    assert result["decision"] == "needs_human"
    assert result["discrepancy_type"] == "ai_tool_failure"
    assert result["rupee_impact"] == 1000.0
    assert "Invalid arguments" in result["agent_trace"][0]["result"]["error"]


def test_tool_iteration_limit_returns_needs_human(
    monkeypatch: Any,
    tool_context: AgentToolContext,
) -> None:
    responses = [
        _tool_use("get_invoice", {"invoice_id": "INV001"}, f"toolu_{index}")
        for index in range(ai_agent.MAX_TOOL_ITERATIONS)
    ]
    calls = _mock_claude(monkeypatch, responses)

    result = reconcile_ambiguous_case_with_tools(
        _case_context(include_impact=True),
        tool_context=tool_context,
    )

    assert result["decision"] == "needs_human"
    assert result["discrepancy_type"] == "tool_iteration_limit_reached"
    assert result["rupee_impact"] == 1000.0
    assert len(result["agent_trace"]) == ai_agent.MAX_TOOL_ITERATIONS
    assert len(calls) == ai_agent.MAX_TOOL_ITERATIONS


def test_claude_cannot_override_deterministic_tool_rupee_impact(
    monkeypatch: Any,
    tool_context: AgentToolContext,
) -> None:
    _mock_claude(
        monkeypatch,
        [
            _tool_use(
                "calculate_financial_impact",
                {"billed_amount": 11500.0, "expected_amount": 10500.0},
            ),
            _final(
                _decision(
                    decision="flag",
                    discrepancy_type="rate_mismatch",
                    reason="The invoice is overbilled.",
                    confidence=0.88,
                    rupee_impact=1300.0,
                    evidence=[
                        {
                            "source": "invoice",
                            "field": "rupee_impact",
                            "value": "1000.0",
                        }
                    ],
                )
            ),
        ],
    )

    result = reconcile_ambiguous_case_with_tools(
        _case_context(),
        tool_context=tool_context,
    )

    assert result["decision"] == "needs_human"
    assert result["discrepancy_type"] == "ai_response_invalid"
    assert result["rupee_impact"] == 1000.0
    assert "deterministic impact" in result["reason"]


def test_claude_cannot_invent_evidence(
    monkeypatch: Any,
    tool_context: AgentToolContext,
) -> None:
    _mock_claude(
        monkeypatch,
        [
            _final(
                _decision(
                    decision="flag",
                    discrepancy_type="historical_duplicate",
                    reason="A historical invoice supposedly matches.",
                    confidence=0.75,
                    rupee_impact=0.0,
                    evidence=[
                        {
                            "source": "history",
                            "field": "invoice_id",
                            "value": "INV999",
                        }
                    ],
                )
            )
        ],
    )

    result = reconcile_ambiguous_case_with_tools(
        _case_context(),
        tool_context=tool_context,
    )

    assert result["decision"] == "needs_human"
    assert result["discrepancy_type"] == "ai_response_invalid"
    assert "evidence that was not supplied" in result["reason"]


def test_claude_api_failure_returns_needs_human(
    monkeypatch: Any,
    tool_context: AgentToolContext,
) -> None:
    def fake_post_to_claude(
        payload: dict[str, Any],
        *,
        api_key: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        raise ClaudeAPIError("HTTP 503")

    monkeypatch.setenv("CLAUDE_API_KEY", "test-claude-key")
    monkeypatch.setattr(ai_agent, "_post_to_claude", fake_post_to_claude)

    result = reconcile_ambiguous_case_with_tools(
        _case_context(include_impact=True),
        tool_context=tool_context,
    )

    assert result["decision"] == "needs_human"
    assert result["discrepancy_type"] == "ai_agent_unavailable"
    assert result["rupee_impact"] == 1000.0
    assert result["agent_trace"] == []


def test_full_mocked_agent_investigation_succeeds(
    monkeypatch: Any,
    tool_context: AgentToolContext,
) -> None:
    _mock_claude(
        monkeypatch,
        [
            _tool_use(
                "get_rate_card",
                {
                    "transporter": "Bharat Roadlines",
                    "origin": "Pune",
                    "destination": "Mumbai",
                    "vehicle_type": "20-ton trailer",
                },
                "toolu_rate",
            ),
            _tool_use(
                "calculate_financial_impact",
                {"billed_amount": 11500.0, "expected_amount": 10500.0},
                "toolu_impact",
            ),
            _final(
                _decision(
                    decision="flag",
                    discrepancy_type="rate_mismatch",
                    reason=(
                        "The retrieved contract exists and deterministic "
                        "impact confirms overbilling."
                    ),
                    confidence=0.93,
                    rupee_impact=1000.0,
                    evidence=[
                        {
                            "source": "rate_card",
                            "field": "rate_id",
                            "value": "RC001",
                        },
                        {
                            "source": "invoice",
                            "field": "rupee_impact",
                            "value": "1000.0",
                        },
                    ],
                )
            ),
        ],
    )

    result = reconcile_ambiguous_case_with_tools(
        _case_context(),
        tool_context=tool_context,
    )

    assert result["decision"] == "flag"
    assert result["discrepancy_type"] == "rate_mismatch"
    assert result["rupee_impact"] == 1000.0
    assert [entry["tool"] for entry in result["agent_trace"]] == [
        "get_rate_card",
        "calculate_financial_impact",
    ]
