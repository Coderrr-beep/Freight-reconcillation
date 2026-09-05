"""Normalize transporter names, locations, and other fields for matching."""

from __future__ import annotations

import re
from datetime import date

from models.input import ReconciliationInput
from models.invoice import DispatchRecord, Invoice
from models.normalized import (
    NormalizedDispatchRecord,
    NormalizedInvoice,
    NormalizedRateCardEntry,
    NormalizedReconciliationInput,
)
from models.rate_card import RateCardEntry

LEGAL_SUFFIX_PATTERNS: tuple[str, ...] = (
    r"private\s+limited",
    r"pvt\.?\s+ltd\.?",
    r"pvt\.?\s+limited",
    r"limited",
    r"ltd\.?",
    r"company",
    r"co\.?",
    r"llp",
    r"inc\.?",
    r"llc",
)


def collapse_whitespace(value: str) -> str:
    """Collapse repeated internal whitespace and trim edges."""
    return " ".join(value.split())


def normalize_route(value: str) -> str:
    """Normalize origin/destination strings with consistent casing and spacing."""
    cleaned = collapse_whitespace(value.strip(" ,.;"))
    return cleaned.title()


def normalize_vehicle_type(value: str) -> str:
    """Normalize vehicle type casing, spacing, and hyphen formatting."""
    cleaned = collapse_whitespace(value)
    cleaned = re.sub(r"\s*-\s*", "-", cleaned)
    return cleaned.lower()


def strip_legal_suffixes(value: str) -> str:
    """Remove common legal entity suffixes from the end of a transporter name."""
    result = collapse_whitespace(value)

    changed = True
    while changed:
        changed = False
        for pattern in LEGAL_SUFFIX_PATTERNS:
            updated = re.sub(rf"\s+{pattern}$", "", result, flags=re.IGNORECASE).strip(" ,.;")
            if updated != result:
                result = updated
                changed = True
                break

    return result


def normalize_transporter_name(value: str) -> str:
    """Normalize transporter name casing, punctuation, and legal suffixes."""
    without_suffix = strip_legal_suffixes(value)
    normalized = collapse_whitespace(without_suffix.strip(" ,.;"))
    return normalized.title()


def normalize_lr_number(value: str) -> str:
    """Normalize LR numbers with consistent spacing and casing."""
    return collapse_whitespace(value).upper()


def normalize_numeric(value: float | int | str) -> float:
    """Coerce numeric values to float, stripping common formatting."""
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not cleaned:
            raise ValueError("Numeric value cannot be empty")
        return float(cleaned)
    return float(value)


def normalize_monetary_value(value: float | int | str) -> float:
    """Normalize monetary amounts to a float rounded to two decimal places."""
    return round(normalize_numeric(value), 2)


def normalize_weight(value: float | int | str) -> float:
    """Normalize weight values to a float rounded to two decimal places."""
    return round(normalize_numeric(value), 2)


def normalize_date(value: date | str) -> tuple[date, str]:
    """Normalize invoice dates to a date object and ISO-8601 string."""
    if isinstance(value, str):
        parsed = date.fromisoformat(value.strip())
    else:
        parsed = value
    return parsed, parsed.isoformat()


def normalize_invoice(invoice: Invoice) -> NormalizedInvoice:
    """Return a normalized view of an invoice while preserving the raw record."""
    normalized_date, date_iso = normalize_date(invoice.invoice_date)

    return NormalizedInvoice(
        raw=invoice,
        transporter_name=normalize_transporter_name(invoice.transporter_name),
        origin=normalize_route(invoice.origin),
        destination=normalize_route(invoice.destination),
        vehicle_type=normalize_vehicle_type(invoice.vehicle_type),
        weight_billed_tons=normalize_weight(invoice.weight_billed_tons),
        rate_applied_per_ton=normalize_monetary_value(invoice.rate_applied_per_ton),
        fixed_charge_applied=normalize_monetary_value(invoice.fixed_charge_applied),
        total_amount=normalize_monetary_value(invoice.total_amount),
        invoice_date=normalized_date,
        invoice_date_iso=date_iso,
        lr_number=normalize_lr_number(invoice.lr_number),
    )


def normalize_rate_card(entry: RateCardEntry) -> NormalizedRateCardEntry:
    """Return a normalized view of a rate card entry while preserving the raw record."""
    return NormalizedRateCardEntry(
        raw=entry,
        transporter=normalize_transporter_name(entry.transporter),
        origin=normalize_route(entry.origin),
        destination=normalize_route(entry.destination),
        vehicle_type=normalize_vehicle_type(entry.vehicle_type),
        rate_per_ton=normalize_monetary_value(entry.rate_per_ton),
        fixed_charge=normalize_monetary_value(entry.fixed_charge),
        acceptable_weight_variance_pct=normalize_numeric(entry.acceptable_weight_variance_pct),
    )


def normalize_dispatch_record(record: DispatchRecord) -> NormalizedDispatchRecord:
    """Return a normalized view of a dispatch record while preserving the raw record."""
    return NormalizedDispatchRecord(
        raw=record,
        lr_number=normalize_lr_number(record.lr_number),
        dispatched_weight_tons=normalize_weight(record.dispatched_weight_tons),
    )


def normalize_reconciliation_input(
    data: ReconciliationInput,
) -> NormalizedReconciliationInput:
    """Normalize all records in a reconciliation input bundle."""
    return NormalizedReconciliationInput(
        rate_cards=[normalize_rate_card(entry) for entry in data.rate_cards],
        invoices=[normalize_invoice(invoice) for invoice in data.invoices],
        dispatch_records=[
            normalize_dispatch_record(record) for record in data.dispatch_records
        ],
    )
