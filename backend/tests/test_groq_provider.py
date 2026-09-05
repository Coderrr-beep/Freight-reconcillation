from __future__ import annotations

import json
from datetime import date
from typing import Any

from models.invoice import DispatchRecord, Invoice
from models.rate_card import RateCardEntry
from services import ai_agent
from services.agent_tools import AgentToolContext
from services.ai_agent import reconcile_ambiguous_case, reconcile_ambiguous_case_with_tools


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = json.dumps(payload).encode()

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def _context() -> dict[str, Any]:
    return {
        "invoice_data": {
            "invoice_id": "INV001",
            "lr_number": "LR100001",
            "transporter_name": "Bharat Roadlines",
            "origin": "Pune",
            "destination": "Mumbai",
            "vehicle_type": "20-ton trailer",
            "total_amount": 10500.0,
        },
        "normalized_invoice_data": None,
        "matched_rate_card": None,
        "dispatch_record": None,
        "deterministic_checks_performed": ["rate_card_match"],
        "detected_ambiguity": "The contract requires additional review.",
        "calculated_variance": None,
        "calculated_financial_impact": None,
        "relevant_evidence": [
            {"source": "invoice", "field": "invoice_id", "value": "INV001"}
        ],
    }


def _tool_context() -> AgentToolContext:
    return AgentToolContext.from_raw_records(
        invoices=[
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
            )
        ],
        rate_cards=[
            RateCardEntry(
                rate_id="RC001",
                transporter="Bharat Roadlines",
                origin="Pune",
                destination="Mumbai",
                vehicle_type="20-ton trailer",
                rate_per_ton=1000.0,
                fixed_charge=500.0,
                acceptable_weight_variance_pct=3.0,
            )
        ],
        dispatch_records=[
            DispatchRecord(lr_number="LR100001", dispatched_weight_tons=10.0)
        ],
    )


def _final_response() -> dict[str, Any]:
    return {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "decision": "clear",
                            "discrepancy_type": "none",
                            "reason": "The supplied invoice evidence is consistent.",
                            "confidence": 0.8,
                            "rupee_impact": 0.0,
                            "evidence": [
                                {
                                    "source": "invoice",
                                    "field": "invoice_id",
                                    "value": "INV001",
                                }
                            ],
                            "agent_trace": [],
                        }
                    ),
                },
            }
        ]
    }


def test_groq_is_selected_when_only_groq_key_is_set(monkeypatch: Any) -> None:
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")

    assert ai_agent._get_provider() == "groq"
    assert ai_agent._get_api_key() == "groq-test-key"
    assert ai_agent._get_model_name() == "openai/gpt-oss-20b"


def test_groq_tool_call_is_adapted_and_executed(monkeypatch: Any) -> None:
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    responses = [
        {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "get_invoice",
                                    "arguments": '{"invoice_id":"INV001"}',
                                },
                            }
                        ],
                    },
                }
            ]
        },
        _final_response(),
        _final_response(),
    ]

    def fake_urlopen(request: Any, timeout: float) -> _FakeHTTPResponse:
        assert request.full_url == ai_agent.GROQ_API_URL
        assert request.get_header("Authorization") == "Bearer groq-test-key"
        return _FakeHTTPResponse(responses.pop(0))

    monkeypatch.setattr(ai_agent.urllib.request, "urlopen", fake_urlopen)
    result = reconcile_ambiguous_case_with_tools(
        _context(),
        tool_context=_tool_context(),
    )

    assert result["decision"] == "clear"
    assert result["agent_trace"][0]["tool"] == "get_invoice"
    assert result["agent_trace"][0]["result"]["found"] is True


def test_groq_final_decision_without_tool_calls_is_parsed(monkeypatch: Any) -> None:
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    monkeypatch.setattr(
        ai_agent.urllib.request,
        "urlopen",
        lambda request, timeout: _FakeHTTPResponse(_final_response()),
    )

    result = reconcile_ambiguous_case(_context())

    assert result["decision"] == "clear"
    assert result["agent_trace"] == []
    assert result["rupee_impact"] == 0.0
