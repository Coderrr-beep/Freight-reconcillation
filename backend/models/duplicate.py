from typing import Literal

from pydantic import BaseModel, Field

DuplicateStatus = Literal["unique", "duplicate_original", "potential_duplicate"]


class DuplicateLRCase(BaseModel):
    """Grouped view of invoices sharing the same LR number."""

    lr_number: str
    duplicate_status: Literal["potential_duplicate"] = "potential_duplicate"
    invoice_ids: list[str] = Field(min_length=2)
    invoice_count: int = Field(ge=2)
    reason: str


class InvoiceDuplicateResult(BaseModel):
    """Per-invoice duplicate-billing signal for the reconciliation layer."""

    invoice_id: str
    lr_number: str
    duplicate_status: DuplicateStatus
    related_invoice_ids: list[str] = Field(default_factory=list)
    reason: str | None = None


class DuplicateDetectionResult(BaseModel):
    """ LR detection output across the invoice set."""

    duplicate_lr_cases: list[DuplicateLRCase]
    invoice_results: list[InvoiceDuplicateResult]

    @property
    def potential_duplicate_count(self) -> int:
        return sum(
            1 for result in self.invoice_results if result.duplicate_status == "potential_duplicate"
        )
