from pydantic import BaseModel, Field


class RateCardEntry(BaseModel):
    """Contracted freight rate for a transporter, route, and vehicle type."""

    rate_id: str
    transporter: str
    origin: str
    destination: str
    vehicle_type: str
    rate_per_ton: float = Field(ge=0)
    fixed_charge: float = Field(ge=0)
    acceptable_weight_variance_pct: float = Field(ge=0)
