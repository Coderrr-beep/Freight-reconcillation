from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

DiscrepancyType = Literal[
    "clean",
    "transporter_name_variant",
    "rate_mismatch",
    "weight_variance_acceptable",
    "weight_variance_excess",
    "duplicate_billing",
    "no_contracted_rate_found",
]

ExpectedAction = Literal[
    "auto_clear",
    "auto_clear_after_fuzzy_match",
    "flag",
    "needs_human",
]

ReconciliationStatus = Literal["auto_clear", "flagged", "needs_human"]

EngineDiscrepancyType = Literal[
    "none",
    "rate_mismatch",
    "weight_variance",
    "duplicate_billing",
    "no_contracted_rate_found",
    "multiple_issues",
]

ConfidenceLevel = Literal["high", "medium", "low"]


class GroundTruth(BaseModel):
    """Evaluation labels from invoices.json — used only by the scoring module."""

    is_discrepancy: Optional[bool] = None
    type: DiscrepancyType
    expected_action: ExpectedAction
    rupee_impact: Optional[float] = None


class ReconciliationEvidence(BaseModel):
    """Structured supporting data for a reconciliation decision."""

    match_status: Optional[str] = None
    match_method: Optional[str] = None
    similarity_score: Optional[float] = Field(default=None, ge=0, le=100)
    billed_rate_per_ton: Optional[float] = None
    contracted_rate_per_ton: Optional[float] = None
    billed_fixed_charge: Optional[float] = None
    contracted_fixed_charge: Optional[float] = None
    billed_weight_tons: Optional[float] = None
    dispatched_weight_tons: Optional[float] = None
    weight_for_expected_amount_tons: Optional[float] = None
    weight_variance_pct: Optional[float] = None
    acceptable_weight_variance_pct: Optional[float] = None
    expected_amount: Optional[float] = None
    billed_amount: Optional[float] = None
    rate_impact: Optional[float] = None
    weight_impact: Optional[float] = None
    duplicate_related_invoice_ids: list[str] = Field(default_factory=list)
    duplicate_reason: Optional[str] = None
    match_reason: Optional[str] = None
    issues_detected: list[str] = Field(default_factory=list)


class DeterministicReconciliationResult(BaseModel):
    """Deterministic reconciliation outcome for a single invoice."""

    invoice_id: str
    lr_number: str
    status: ReconciliationStatus
    discrepancy_type: EngineDiscrepancyType
    rupee_impact: float
    matched_rate_id: Optional[str] = None
    checks_performed: list[str]
    explanation: str
    confidence: ConfidenceLevel
    evidence: ReconciliationEvidence


class InvoiceReconciliationResult(BaseModel):
    """Reconciliation outcome for a single invoice."""

    invoice_id: str
    lr_number: str
    is_discrepancy: Optional[bool] = None
    discrepancy_type: DiscrepancyType
    recommended_action: ExpectedAction
    rupee_impact: Optional[float] = None
    matched_rate_id: Optional[str] = None
    notes: Optional[str] = None


class ReconciliationSummary(BaseModel):
    """Batch reconciliation output."""

    total_invoices: int = Field(ge=0)
    auto_clear: int = Field(ge=0)
    flagged: int = Field(ge=0)
    needs_human: int = Field(ge=0)
    results: list[DeterministicReconciliationResult]

    @property
    def cleared(self) -> int:
        return self.auto_clear
ResolvedBy = Literal["deterministic", "ai_agent"]


class MergedInvoiceResult(BaseModel):
    """Final per-invoice result after merging deterministic + AI agent output."""

    invoice_id: str
    lr_number: str
    status: ReconciliationStatus
    discrepancy_type: str
    rupee_impact: float
    matched_rate_id: Optional[str] = None
    explanation: str
    resolved_by: ResolvedBy
    deterministic_result: DeterministicReconciliationResult
    ai_result: Optional[dict[str, Any]] = None


class BatchResult(BaseModel):
    """Full batch output, stored in-memory keyed by batch_id."""

    batch_id: str
    total_invoices: int = Field(ge=0)
    auto_clear: int = Field(ge=0)
    flagged: int = Field(ge=0)
    needs_human: int = Field(ge=0)
    results: list[MergedInvoiceResult]


ScoredClassification = Literal[
    "true_positive",
    "false_positive",
    "true_negative",
    "false_negative",
    "correctly_routed_to_exception",
    "incorrectly_force_resolved",
    "unresolved_resolvable_case",
]


class ScoredInvoiceResult(BaseModel):
    """Per-invoice comparison between the system's prediction and ground truth."""

    invoice_id: str
    predicted_status: ReconciliationStatus
    actual_is_discrepancy: Optional[bool]
    actual_type: DiscrepancyType
    classification: ScoredClassification
    correct: bool


class ScoringReport(BaseModel):
    """Batch-level scoring output, computed against ground truth (data/invoices.json)."""

    batch_id: str
    total_invoices: int = Field(ge=0)
    total_scoreable_invoices: int = Field(ge=0)
    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    true_negative: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    correctly_routed_to_exception: int = Field(ge=0)
    incorrectly_force_resolved: int = Field(ge=0)
    unresolved_resolvable_case: int = Field(ge=0)
    precision: Optional[float] = None
    recall: Optional[float] = None
    match_rate: Optional[float] = None
    false_positive_cost_rupees: float
    total_rupee_impact_correctly_caught: float
    breakdown: list[ScoredInvoiceResult]