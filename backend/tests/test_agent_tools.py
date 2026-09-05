from __future__ import annotations

from datetime import date

import pytest

from models.invoice import DispatchRecord, Invoice
from models.rate_card import RateCardEntry
from services.agent_tools import (
    AgentToolContext,
    InvalidAgentToolArgumentsError,
    TOOL_REGISTRY,
    UnknownAgentToolError,
    calculate_financial_impact,
    calculate_weight_variance,
    execute_tool,
    get_claude_tool_definitions,
    get_dispatch_record,
    get_invoice,
    get_rate_card,
    search_similar_invoices,
)


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
        Invoice(
            invoice_id="INV002",
            lr_number=" lr100002 ",
            transporter_name="Bharat Road Lines",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="20-ton trailer",
            weight_billed_tons=11.0,
            rate_applied_per_ton=1000.0,
            fixed_charge_applied=500.0,
            total_amount=11500.0,
            invoice_date=date(2026, 6, 2),
        ),
        Invoice(
            invoice_id="INV003",
            lr_number="LR100003",
            transporter_name="Speedway Carriers",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="20-ton trailer",
            weight_billed_tons=8.0,
            rate_applied_per_ton=1200.0,
            fixed_charge_applied=600.0,
            total_amount=10200.0,
            invoice_date=date(2026, 6, 3),
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
        RateCardEntry(
            rate_id="RC002",
            transporter="Speedway Carriers",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="20-ton trailer",
            rate_per_ton=1200.0,
            fixed_charge=600.0,
            acceptable_weight_variance_pct=2.5,
        ),
    ]
    dispatch_records = [
        DispatchRecord(lr_number="LR100001", dispatched_weight_tons=10.0),
        DispatchRecord(lr_number="LR100002", dispatched_weight_tons=10.0),
    ]
    return AgentToolContext.from_raw_records(
        invoices=invoices,
        rate_cards=rate_cards,
        dispatch_records=dispatch_records,
    )


def test_get_invoice_returns_raw_and_normalized_invoice(tool_context: AgentToolContext) -> None:
    result = get_invoice("INV002", context=tool_context)

    assert result["found"] is True
    assert result["invoice"]["lr_number"] == " lr100002 "
    assert result["normalized_invoice"]["lr_number"] == "LR100002"
    assert result["normalized_invoice"]["transporter_name"] == "Bharat Road Lines"


def test_get_rate_card_returns_matching_contracts(tool_context: AgentToolContext) -> None:
    result = get_rate_card(
        "Bharat Roadlines Pvt Ltd",
        "pune",
        "MUMBAI",
        "20 - ton trailer",
        context=tool_context,
    )

    assert result["found"] is True
    assert result["normalized_query"] == {
        "transporter": "Bharat Roadlines",
        "origin": "Pune",
        "destination": "Mumbai",
        "vehicle_type": "20-ton trailer",
    }
    assert result["contracts"][0]["rate_id"] == "RC001"
    assert {item["rate_id"] for item in result["route_vehicle_candidates"]} == {
        "RC001",
        "RC002",
    }


def test_get_dispatch_record_returns_weighbridge_record(tool_context: AgentToolContext) -> None:
    result = get_dispatch_record(" lr100002 ", context=tool_context)

    assert result["found"] is True
    assert result["dispatch_record"]["lr_number"] == "LR100002"
    assert result["dispatch_record"]["dispatched_weight_tons"] == 10.0


def test_calculate_weight_variance_is_deterministic() -> None:
    result = calculate_weight_variance(
        billed_weight=11.0,
        dispatched_weight=10.0,
        tolerance=3.0,
    )

    assert result["variance"] == 1.0
    assert result["variance_percent"] == 10.0
    assert result["within_tolerance"] is False
    assert "outside the 3.0% tolerance" in result["explanation"]


def test_calculate_financial_impact_is_deterministic() -> None:
    result = calculate_financial_impact(
        billed_amount=11500.0,
        expected_amount=10500.0,
    )

    assert result == {"rupee_impact": 1000.0}


def test_search_similar_invoices_returns_existing_records(tool_context: AgentToolContext) -> None:
    result = search_similar_invoices(
        "Bharat Roadlines",
        "Pune",
        "Mumbai",
        "20-ton trailer",
        limit=2,
        context=tool_context,
    )

    assert result["count"] == 2
    assert [record["invoice_id"] for record in result["records"]] == ["INV001", "INV002"]
    assert all(record["origin"] == "Pune" for record in result["records"])


def test_execute_tool_rejects_unknown_tools() -> None:
    with pytest.raises(UnknownAgentToolError, match="Unknown tool"):
        execute_tool("read_file", {})


def test_execute_tool_rejects_invalid_arguments() -> None:
    with pytest.raises(InvalidAgentToolArgumentsError, match="Invalid arguments"):
        execute_tool("calculate_weight_variance", {"billed_weight": 10.0})


def test_tool_registry_exposes_only_controlled_tools() -> None:
    assert set(TOOL_REGISTRY) == {
        "get_invoice",
        "get_rate_card",
        "get_dispatch_record",
        "calculate_weight_variance",
        "calculate_financial_impact",
        "search_similar_invoices",
    }


def test_claude_tool_definitions_use_safe_schemas() -> None:
    serialized_definitions = str(get_claude_tool_definitions())

    assert "read_file" not in serialized_definitions
    assert "python" not in serialized_definitions
    assert "minLength" not in serialized_definitions
    assert "minimum" not in serialized_definitions
    assert "exclusiveMinimum" not in serialized_definitions
