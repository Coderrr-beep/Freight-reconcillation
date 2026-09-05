from datetime import date

from pydantic import BaseModel, Field


class Invoice(BaseModel):
    """Transporter invoice as provided to the reconciliation engine."""

    invoice_id: str
    lr_number: str
    transporter_name: str
    origin: str
    destination: str
    vehicle_type: str
    weight_billed_tons: float = Field(gt=0)
    rate_applied_per_ton: float = Field(ge=0)
    fixed_charge_applied: float = Field(ge=0)
    total_amount: float = Field(ge=0)
    invoice_date: date


class DispatchRecord(BaseModel):
    """Weighbridge / dispatch record keyed by LR number."""

    lr_number: str
    dispatched_weight_tons: float = Field(gt=0)
