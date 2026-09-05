from typing import Literal, Optional

from pydantic import BaseModel, Field

from .normalized import NormalizedRateCardEntry

MatchStatus = Literal["matched", "no_match"]
MatchMethod = Literal["exact", "fuzzy"]


class RateCardMatchResult(BaseModel):
    """Result of matching an invoice to a contracted rate-card row."""

    invoice_id: str
    lr_number: str
    match_status: MatchStatus
    matched_rate_card: Optional[NormalizedRateCardEntry] = None
    match_method: Optional[MatchMethod] = None
    similarity_score: Optional[float] = Field(default=None, ge=0, le=100)
    is_reliable: bool
    reason: Optional[str] = None
