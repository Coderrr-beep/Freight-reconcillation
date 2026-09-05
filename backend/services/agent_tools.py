"""Controlled tools available to the AI reconciliation agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from rapidfuzz import fuzz

from models.invoice import DispatchRecord, Invoice
from models.normalized import (
    NormalizedDispatchRecord,
    NormalizedInvoice,
    NormalizedRateCardEntry,
)
from models.rate_card import RateCardEntry
from services.ingestion import load_reconciliation_input
from services.normalization import (
    normalize_dispatch_record,
    normalize_invoice,
    normalize_rate_card,
    normalize_route,
    normalize_transporter_name,
    normalize_vehicle_type,
    normalize_weight,
)


class AgentToolError(Exception):
    """Base class for controlled tool failures."""


class UnknownAgentToolError(AgentToolError):
    """Raised when Claude requests a tool outside the registry."""


class InvalidAgentToolArgumentsError(AgentToolError):
    """Raised when Claude supplies malformed tool arguments."""


class AgentToolExecutionError(AgentToolError):
    """Raised when a registered tool fails while executing."""


class GetInvoiceArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_id: str = Field(min_length=1)


class GetRateCardArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transporter: str = Field(min_length=1)
    origin: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    vehicle_type: str = Field(min_length=1)


class GetDispatchRecordArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lr_number: str = Field(min_length=1)


class CalculateWeightVarianceArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    billed_weight: float = Field(gt=0)
    dispatched_weight: float = Field(gt=0)
    tolerance: float = Field(ge=0)


class CalculateFinancialImpactArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    billed_amount: float = Field(ge=0)
    expected_amount: float = Field(ge=0)


class SearchSimilarInvoicesArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transporter: str = Field(min_length=1)
    origin: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    vehicle_type: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=25)


@dataclass(frozen=True)
class AgentToolContext:
    """Normalized data available to controlled agent tools."""

    invoices: list[NormalizedInvoice]
    rate_cards: list[NormalizedRateCardEntry]
    dispatch_records: list[NormalizedDispatchRecord]

    @classmethod
    def from_raw_records(
        cls,
        *,
        invoices: list[Invoice],
        rate_cards: list[RateCardEntry],
        dispatch_records: list[DispatchRecord],
    ) -> "AgentToolContext":
        return cls(
            invoices=[normalize_invoice(invoice) for invoice in invoices],
            rate_cards=[normalize_rate_card(rate_card) for rate_card in rate_cards],
            dispatch_records=[
                normalize_dispatch_record(record) for record in dispatch_records
            ],
        )


@dataclass(frozen=True)
class AgentTool:
    """Registry entry for one controlled tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    argument_model: type[BaseModel]
    function: Callable[..., dict[str, Any]]

    def claude_definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": _claude_compatible_schema(self.input_schema),
            "strict": True,
        }


def load_default_tool_context() -> AgentToolContext:
    """Load the fixed engine input files for controlled tool execution."""
    data = load_reconciliation_input()
    return AgentToolContext.from_raw_records(
        invoices=data.invoices,
        rate_cards=data.rate_cards,
        dispatch_records=data.dispatch_records,
    )


def get_invoice(
    invoice_id: str,
    *,
    context: AgentToolContext | None = None,
) -> dict[str, Any]:
    """Return raw and normalized invoice information for one invoice ID."""
    tool_context = context or load_default_tool_context()
    requested_invoice_id = invoice_id.strip()

    for invoice in tool_context.invoices:
        if invoice.raw.invoice_id == requested_invoice_id:
            return {
                "found": True,
                "invoice": invoice.raw.model_dump(mode="json"),
                "normalized_invoice": _normalized_invoice_payload(invoice),
            }

    return {
        "found": False,
        "invoice_id": requested_invoice_id,
        "invoice": None,
        "normalized_invoice": None,
    }


def get_rate_card(
    transporter: str,
    origin: str,
    destination: str,
    vehicle_type: str,
    *,
    context: AgentToolContext | None = None,
) -> dict[str, Any]:
    """Return relevant rate-card contracts for a transporter, route, and vehicle."""
    tool_context = context or load_default_tool_context()
    normalized_query = {
        "transporter": normalize_transporter_name(transporter),
        "origin": normalize_route(origin),
        "destination": normalize_route(destination),
        "vehicle_type": normalize_vehicle_type(vehicle_type),
    }

    route_vehicle_candidates = [
        rate_card
        for rate_card in tool_context.rate_cards
        if rate_card.origin == normalized_query["origin"]
        and rate_card.destination == normalized_query["destination"]
        and rate_card.vehicle_type == normalized_query["vehicle_type"]
    ]
    exact_matches = [
        rate_card
        for rate_card in route_vehicle_candidates
        if rate_card.transporter == normalized_query["transporter"]
    ]

    sorted_candidates = sorted(
        route_vehicle_candidates,
        key=lambda rate_card: (
            fuzz.WRatio(normalized_query["transporter"], rate_card.transporter),
            rate_card.raw.rate_id,
        ),
        reverse=True,
    )

    return {
        "found": bool(exact_matches),
        "normalized_query": normalized_query,
        "contracts": [_rate_card_payload(rate_card) for rate_card in exact_matches],
        "route_vehicle_candidates": [
            {
                **_rate_card_payload(rate_card),
                "transporter_similarity": round(
                    float(fuzz.WRatio(normalized_query["transporter"], rate_card.transporter)),
                    2,
                ),
            }
            for rate_card in sorted_candidates
        ],
    }


def get_dispatch_record(
    lr_number: str,
    *,
    context: AgentToolContext | None = None,
) -> dict[str, Any]:
    """Return the dispatch/weighbridge record for one LR number."""
    tool_context = context or load_default_tool_context()
    normalized_lr_number = lr_number.strip().upper()

    for record in tool_context.dispatch_records:
        if record.lr_number == normalized_lr_number:
            return {
                "found": True,
                "dispatch_record": {
                    "lr_number": record.lr_number,
                    "dispatched_weight_tons": record.dispatched_weight_tons,
                    "raw": record.raw.model_dump(mode="json"),
                },
            }

    return {
        "found": False,
        "lr_number": normalized_lr_number,
        "dispatch_record": None,
    }


def calculate_weight_variance(
    billed_weight: float,
    dispatched_weight: float,
    tolerance: float,
    *,
    context: AgentToolContext | None = None,
) -> dict[str, Any]:
    """Calculate weight variance using deterministic Python logic."""
    del context

    billed = normalize_weight(billed_weight)
    dispatched = normalize_weight(dispatched_weight)
    variance = round(billed - dispatched, 2)
    variance_percent = round(abs(variance) / dispatched * 100.0, 2)
    within_tolerance = variance_percent <= tolerance

    comparison = "within" if within_tolerance else "outside"
    return {
        "variance": variance,
        "variance_percent": variance_percent,
        "tolerance": tolerance,
        "within_tolerance": within_tolerance,
        "explanation": (
            f"Billed weight differs from dispatched weight by {variance} tons "
            f"({variance_percent}%), which is {comparison} the {tolerance}% tolerance."
        ),
    }


def calculate_financial_impact(
    billed_amount: float,
    expected_amount: float,
    *,
    context: AgentToolContext | None = None,
) -> dict[str, Any]:
    """Calculate rupee impact using deterministic Python logic."""
    del context

    rupee_impact = round(billed_amount - expected_amount, 2)
    return {"rupee_impact": rupee_impact}


def search_similar_invoices(
    transporter: str,
    origin: str,
    destination: str,
    vehicle_type: str,
    limit: int = 5,
    *,
    context: AgentToolContext | None = None,
) -> dict[str, Any]:
    """Search available invoice data for route/vehicle-similar invoices."""
    tool_context = context or load_default_tool_context()
    normalized_transporter = normalize_transporter_name(transporter)
    normalized_origin = normalize_route(origin)
    normalized_destination = normalize_route(destination)
    normalized_vehicle_type = normalize_vehicle_type(vehicle_type)

    route_vehicle_matches = [
        invoice
        for invoice in tool_context.invoices
        if invoice.origin == normalized_origin
        and invoice.destination == normalized_destination
        and invoice.vehicle_type == normalized_vehicle_type
    ]

    ranked = sorted(
        route_vehicle_matches,
        key=lambda invoice: (
            fuzz.WRatio(normalized_transporter, invoice.transporter_name),
            invoice.raw.invoice_id,
        ),
        reverse=True,
    )
    records = []
    for invoice in ranked[:limit]:
        records.append(
            {
                "invoice_id": invoice.raw.invoice_id,
                "lr_number": invoice.lr_number,
                "transporter_name": invoice.raw.transporter_name,
                "normalized_transporter_name": invoice.transporter_name,
                "origin": invoice.origin,
                "destination": invoice.destination,
                "vehicle_type": invoice.vehicle_type,
                "billed_amount": invoice.total_amount,
                "transporter_similarity": round(
                    float(fuzz.WRatio(normalized_transporter, invoice.transporter_name)),
                    2,
                ),
            }
        )

    return {
        "query": {
            "transporter": normalized_transporter,
            "origin": normalized_origin,
            "destination": normalized_destination,
            "vehicle_type": normalized_vehicle_type,
            "limit": limit,
        },
        "records": records,
        "count": len(records),
    }


def get_ollama_tool_definitions() -> list[dict[str, Any]]:
    """Return controlled tool definitions for OpenAI-compatible providers."""
    return [tool.claude_definition() for tool in TOOL_REGISTRY.values()]


def get_groq_tool_definitions() -> list[dict[str, Any]]:
    """Return controlled tool definitions for Groq's API."""
    return get_ollama_tool_definitions()


def get_claude_tool_definitions() -> list[dict[str, Any]]:
    """Backward-compatible alias for integrations using the old name."""
    return get_ollama_tool_definitions()


def execute_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    context: AgentToolContext | None = None,
) -> dict[str, Any]:
    """Validate and execute a registered tool call."""
    tool = TOOL_REGISTRY.get(name)
    if tool is None:
        raise UnknownAgentToolError(f"Unknown tool requested: {name}")

    try:
        validated_arguments = tool.argument_model.model_validate(arguments)
    except ValidationError as exc:
        raise InvalidAgentToolArgumentsError(
            f"Invalid arguments for {name}: {exc}"
        ) from exc

    try:
        return tool.function(
            **validated_arguments.model_dump(mode="json"),
            context=context,
        )
    except AgentToolError:
        raise
    except Exception as exc:
        raise AgentToolExecutionError(f"{name} failed: {exc}") from exc


def _normalized_invoice_payload(invoice: NormalizedInvoice) -> dict[str, Any]:
    return {
        "invoice_id": invoice.raw.invoice_id,
        "lr_number": invoice.lr_number,
        "transporter_name": invoice.transporter_name,
        "origin": invoice.origin,
        "destination": invoice.destination,
        "vehicle_type": invoice.vehicle_type,
        "weight_billed_tons": invoice.weight_billed_tons,
        "rate_applied_per_ton": invoice.rate_applied_per_ton,
        "fixed_charge_applied": invoice.fixed_charge_applied,
        "total_amount": invoice.total_amount,
        "invoice_date": invoice.invoice_date_iso,
    }


def _rate_card_payload(rate_card: NormalizedRateCardEntry) -> dict[str, Any]:
    return {
        "rate_id": rate_card.raw.rate_id,
        "transporter": rate_card.transporter,
        "origin": rate_card.origin,
        "destination": rate_card.destination,
        "vehicle_type": rate_card.vehicle_type,
        "rate_per_ton": rate_card.rate_per_ton,
        "fixed_charge": rate_card.fixed_charge,
        "acceptable_weight_variance_pct": rate_card.acceptable_weight_variance_pct,
    }


def _claude_compatible_schema(schema: dict[str, Any]) -> dict[str, Any]:
    unsupported_keywords = {
        "default",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "maxLength",
        "maximum",
        "minLength",
        "minimum",
        "title",
    }

    def strip_unsupported(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: strip_unsupported(nested_value)
                for key, nested_value in value.items()
                if key not in unsupported_keywords
            }
        if isinstance(value, list):
            return [strip_unsupported(item) for item in value]
        return value

    return strip_unsupported(schema)


TOOL_REGISTRY: dict[str, AgentTool] = {
    "get_invoice": AgentTool(
        name="get_invoice",
        description=(
            "Return raw and normalized invoice information for an invoice ID. "
            "Use when invoice details are missing from the ambiguous case context."
        ),
        input_schema=GetInvoiceArguments.model_json_schema(),
        argument_model=GetInvoiceArguments,
        function=get_invoice,
    ),
    "get_rate_card": AgentTool(
        name="get_rate_card",
        description=(
            "Return relevant rate-card contracts for a transporter, origin, "
            "destination, and vehicle type. This does not invent contracts."
        ),
        input_schema=GetRateCardArguments.model_json_schema(),
        argument_model=GetRateCardArguments,
        function=get_rate_card,
    ),
    "get_dispatch_record": AgentTool(
        name="get_dispatch_record",
        description=(
            "Return the dispatch or weighbridge record for an LR number. "
            "Use this before reasoning about weight variance."
        ),
        input_schema=GetDispatchRecordArguments.model_json_schema(),
        argument_model=GetDispatchRecordArguments,
        function=get_dispatch_record,
    ),
    "calculate_weight_variance": AgentTool(
        name="calculate_weight_variance",
        description=(
            "Calculate weight variance deterministically from billed weight, "
            "dispatched weight, and tolerance. Claude must not do this math."
        ),
        input_schema=CalculateWeightVarianceArguments.model_json_schema(),
        argument_model=CalculateWeightVarianceArguments,
        function=calculate_weight_variance,
    ),
    "calculate_financial_impact": AgentTool(
        name="calculate_financial_impact",
        description=(
            "Calculate rupee impact deterministically from billed amount and "
            "expected amount. Claude must not do this math."
        ),
        input_schema=CalculateFinancialImpactArguments.model_json_schema(),
        argument_model=CalculateFinancialImpactArguments,
        function=calculate_financial_impact,
    ),
    "search_similar_invoices": AgentTool(
        name="search_similar_invoices",
        description=(
            "Search available invoice data for similar transporter, route, and "
            "vehicle records. Return only existing structured records."
        ),
        input_schema=SearchSimilarInvoicesArguments.model_json_schema(),
        argument_model=SearchSimilarInvoicesArguments,
        function=search_similar_invoices,
    ),
}
