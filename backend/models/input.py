from pydantic import BaseModel

from .invoice import DispatchRecord, Invoice
from .rate_card import RateCardEntry


class ReconciliationInput(BaseModel):
    """Validated engine input loaded from the three JSON source files."""

    rate_cards: list[RateCardEntry]
    invoices: list[Invoice]
    dispatch_records: list[DispatchRecord]
