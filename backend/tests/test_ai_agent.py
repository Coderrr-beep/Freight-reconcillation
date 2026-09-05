from __future__ import annotations

import json
from typing import Any

from services import ai_agent
from services.ai_agent import (
    AI_RECONCILIATION_OUTPUT_SCHEMA,
    ClaudeAPIError,
    reconcile_ambiguous_case,
)


def _case_context() -> dict[str, Any]:
    return {
        "invoice_data": {
            "invoice_id": "INV9001",
            "lr_number": "LR900001",
            "transporter_name": "Bharat Road Lines",
            "origin": "Pune",
            "destination": "Mumbai",
            "vehicle_type": "20-ton trailer",
            "total_amount": 11500.0,
        },
        "normalized_invoice_data": {
            "invoice_id": "INV9001",
            "lr_number": "LR900001",
            "transporter_name": "Bharat Road Lines",
            "origin": "Pune",
            "destination": "Mumbai",
            "vehicle_type": "20-ton trailer",
        },
        "matched_rate_card": {
            "rate_id": "RC001",
            "transporter": "Bharat Roadlines",
            "origin": "Pune",
            "destination": "Mumbai",
            "vehicle_type": "20-ton trailer",
            "rate_per_ton": 1000.0,
            "fixed_charge": 500.0,
        },
        "dispatch_record": {
            "lr_number": "LR900001",
            "dispatched_weight_tons": 10.0,
        },
        "deterministic_checks_performed": [
            "rate_card_match",
            "rate_comparison",
            "weight_variance_check",
        ],
        "detected_ambiguity": "Reliable fuzzy transporter match but billing is over contract.",
        "calculated_variance": {
            "weight_variance_pct": 0.0,
            "acceptable_weight_variance_pct": 3.0,
        },
        "calculated_financial_impact": {
            "rupee_impact": 1000.0,
            "expected_amount": 10500.0,
            "billed_amount": 11500.0,
        },
        "relevant_evidence": [
            {
                "source": "invoice",
                "field": "transporter_name",
                "value": "Bharat Road Lines",
            },
            {
                "source": "rate_card",
                "field": "rate_id",
                "value": "RC001",
            },
        ],
    }


def _claude_text(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload),
            }
        ]
    }


def test_reconcile_ambiguous_case_returns_valid_structured_result(
    monkeypatch: Any,
) -> None:
    captured: dict[str, Any] = {}

    def fake_post_to_claude(
        payload: dict[str, Any],
        *,
        api_key: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        captured["payload"] = payload
        captured["api_key"] = api_key
        captured["timeout_seconds"] = timeout_seconds
        return _claude_text(
            {
                "decision": "flag",
                "discrepancy_type": "rate_mismatch",
                "reason": (
                    "The invoice cites a matched contract but billed amount is "
                    "above the deterministic expected amount."
                ),
                "confidence": 0.86,
                "rupee_impact": 1000.0,
                "evidence": [
                    {
                        "source": "invoice",
                        "field": "total_amount",
                        "value": "11500.0",
                    },
                    {
                        "source": "rate_card",
                        "field": "rate_id",
                        "value": "RC001",
                    },
                ],
            }
        )

    monkeypatch.setenv("CLAUDE_API_KEY", "test-claude-key")
    monkeypatch.setattr(ai_agent, "_post_to_claude", fake_post_to_claude)

    result = reconcile_ambiguous_case(_case_context())

    assert result == {
        "decision": "flag",
        "discrepancy_type": "rate_mismatch",
        "reason": (
            "The invoice cites a matched contract but billed amount is "
            "above the deterministic expected amount."
        ),
        "confidence": 0.86,
        "rupee_impact": 1000.0,
        "evidence": [
            {
                "source": "invoice",
                "field": "total_amount",
                "value": "11500.0",
            },
            {
                "source": "rate_card",
                "field": "rate_id",
                "value": "RC001",
            },
        ],
        "agent_trace": [],
    }
    assert captured["api_key"] == "test-claude-key"
    assert captured["timeout_seconds"] == 10.0
    assert captured["payload"]["temperature"] == 0
    assert captured["payload"]["output_config"]["format"]["type"] == "json_schema"
    sent_schema = captured["payload"]["output_config"]["format"]["schema"]
    assert sent_schema["required"] == AI_RECONCILIATION_OUTPUT_SCHEMA["required"]
    assert sent_schema["properties"]["decision"]["enum"] == ["clear", "flag", "needs_human"]
    assert "minimum" not in sent_schema["properties"]["confidence"]


def test_malformed_claude_json_is_rejected(monkeypatch: Any) -> None:
    def fake_post_to_claude(
        payload: dict[str, Any],
        *,
        api_key: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": "not-json"}]}

    monkeypatch.setenv("CLAUDE_API_KEY", "test-claude-key")
    monkeypatch.setattr(ai_agent, "_post_to_claude", fake_post_to_claude)

    result = reconcile_ambiguous_case(_case_context())

    assert result["decision"] == "needs_human"
    assert result["discrepancy_type"] == "ai_response_invalid"
    assert result["confidence"] == 0.0
    assert result["rupee_impact"] == 0.0
    assert "not valid JSON" in result["reason"]


def test_schema_invalid_claude_response_is_rejected(monkeypatch: Any) -> None:
    def fake_post_to_claude(
        payload: dict[str, Any],
        *,
        api_key: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        return _claude_text(
            {
                "decision": "approve",
                "discrepancy_type": "rate_mismatch",
                "reason": "Looks fine.",
                "confidence": 2.0,
                "rupee_impact": 1000.0,
                "evidence": [
                    {
                        "source": "spreadsheet",
                        "field": "rate_id",
                        "value": "RC001",
                    }
                ],
            }
        )

    monkeypatch.setenv("CLAUDE_API_KEY", "test-claude-key")
    monkeypatch.setattr(ai_agent, "_post_to_claude", fake_post_to_claude)

    result = reconcile_ambiguous_case(_case_context())

    assert result["decision"] == "needs_human"
    assert result["discrepancy_type"] == "ai_response_invalid"
    assert "schema validation" in result["reason"]


def test_ai_cannot_replace_deterministic_rupee_impact(monkeypatch: Any) -> None:
    def fake_post_to_claude(
        payload: dict[str, Any],
        *,
        api_key: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        return _claude_text(
            {
                "decision": "flag",
                "discrepancy_type": "rate_mismatch",
                "reason": "The case should be flagged.",
                "confidence": 0.9,
                "rupee_impact": 9999.0,
                "evidence": [
                    {
                        "source": "invoice",
                        "field": "total_amount",
                        "value": "11500.0",
                    }
                ],
            }
        )

    monkeypatch.setenv("CLAUDE_API_KEY", "test-claude-key")
    monkeypatch.setattr(ai_agent, "_post_to_claude", fake_post_to_claude)

    result = reconcile_ambiguous_case(_case_context())

    assert result["decision"] == "needs_human"
    assert result["discrepancy_type"] == "ai_response_invalid"
    assert result["rupee_impact"] == 0.0
    assert "deterministic impact" in result["reason"]


def test_claude_api_failure_returns_needs_human(monkeypatch: Any) -> None:
    def fake_post_to_claude(
        payload: dict[str, Any],
        *,
        api_key: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        raise ClaudeAPIError("request timed out")

    monkeypatch.setenv("CLAUDE_API_KEY", "test-claude-key")
    monkeypatch.setattr(ai_agent, "_post_to_claude", fake_post_to_claude)

    result = reconcile_ambiguous_case(_case_context())

    assert result["decision"] == "needs_human"
    assert result["discrepancy_type"] == "ai_agent_unavailable"
    assert result["confidence"] == 0.0
    assert result["rupee_impact"] == 0.0
    assert "request timed out" in result["reason"]


def test_required_ollama_api_key_returns_needs_human(monkeypatch: Any) -> None:
    def fake_post_to_claude(
        payload: dict[str, Any],
        *,
        api_key: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        raise AssertionError("Ollama should not be called without a required API key.")

    monkeypatch.setenv("OLLAMA_REQUIRE_API_KEY", "1")
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(ai_agent, "_post_to_claude", fake_post_to_claude)

    result = reconcile_ambiguous_case(_case_context())

    assert result["decision"] == "needs_human"
    assert result["discrepancy_type"] == "ai_agent_unavailable"
    assert result["confidence"] == 0.0
    assert result["rupee_impact"] == 0.0
    assert "LLM API key is not configured" in result["reason"]
