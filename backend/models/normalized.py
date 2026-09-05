from datetime import date

from pydantic import BaseModel, Field

from .invoice import DispatchRecord, Invoice
from .rate_card import RateCardEntry


class NormalizedInvoice(BaseModel):
    """Invoice with normalized fields; raw record is preserved unchanged."""

    raw: Invoice
    transporter_name: str
    origin: str
    destination: str
    vehicle_type: str
    weight_billed_tons: float = Field(gt=0)
    rate_applied_per_ton: float = Field(ge=0)
    fixed_charge_applied: float = Field(ge=0)
    total_amount: float = Field(ge=0)
    invoice_date: date
    invoice_date_iso: str
    lr_number: str


class NormalizedRateCardEntry(BaseModel):
    """Rate card entry with normalized fields; raw record is preserved unchanged."""

    raw: RateCardEntry
    transporter: str
    origin: str
    destination: str
    vehicle_type: str
    rate_per_ton: float = Field(ge=0)
    fixed_charge: float = Field(ge=0)
    acceptable_weight_variance_pct: float = Field(ge=0)


class NormalizedDispatchRecord(BaseModel):
    """Dispatch record with normalized fields; raw record is preserved unchanged."""

    raw: DispatchRecord
    lr_number: str
    dispatched_weight_tons: float = Field(gt=0)


class NormalizedReconciliationInput(BaseModel):
    """Fully normalized engine input with original records retained on each item."""

    rate_cards: list[NormalizedRateCardEntry]
    invoices: list[NormalizedInvoice]
    dispatch_records: list[NormalizedDispatchRecord]
