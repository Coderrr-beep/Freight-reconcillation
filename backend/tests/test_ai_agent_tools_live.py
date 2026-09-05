from __future__ import annotations

import json
import os

import pytest

from services.ai_agent import reconcile_ambiguous_case_with_tools


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_GROQ_TESTS") != "1"
    or not os.getenv("GROQ_API_KEY"),
    reason="Set RUN_LIVE_GROQ_TESTS=1 and GROQ_API_KEY to call Groq.",
)


def test_live_groq_tool_using_reconciliation_response() -> None:
    result = reconcile_ambiguous_case_with_tools(
        {
            "invoice_data": {
                "invoice_id": "INV0001",
                "lr_number": "LR167136",
                "transporter_name": "Ashok Transport Co.",
                "origin": "Coimbatore",
                "destination": "Chennai",
                "vehicle_type": "16-ton truck",
                "weight_billed_tons": 6.72,
                "total_amount": 10818.37,
            },
            "normalized_invoice_data": None,
            "matched_rate_card": None,
            "dispatch_record": None,
            "deterministic_checks_performed": ["rate_card_match"],
            "detected_ambiguity": (
                "Contract details were not supplied in the context. "
                "Use controlled tools to investigate."
            ),
            "calculated_variance": None,
            "calculated_financial_impact": None,
            "relevant_evidence": [
                {
                    "source": "invoice",
                    "field": "invoice_id",
                    "value": "INV0001",
                }
            ],
        }
    )

    print("\nLIVE CLAUDE TOOL-USING RECONCILIATION RESPONSE")
    print(json.dumps(result, indent=2, sort_keys=True))

    assert result["decision"] in {"clear", "flag", "needs_human"}
    assert isinstance(result["discrepancy_type"], str)
    assert isinstance(result["reason"], str)
    assert 0.0 <= result["confidence"] <= 1.0
    assert isinstance(result["rupee_impact"], float | int)
    assert isinstance(result["evidence"], list)
    assert isinstance(result["agent_trace"], list)
