"""Detect duplicate billing across invoices."""

from __future__ import annotations

from collections import defaultdict

from models.duplicate import (
    DuplicateDetectionResult,
    DuplicateLRCase,
    InvoiceDuplicateResult,
)
from models.normalized import NormalizedInvoice


def build_lr_index(
    invoices: list[NormalizedInvoice],
) -> dict[str, list[NormalizedInvoice]]:
    """Index invoices by normalized LR number."""
    index: dict[str, list[NormalizedInvoice]] = defaultdict(list)
    for invoice in invoices:
        index[invoice.lr_number].append(invoice)
    return dict(index)


def detect_duplicate_lrs(invoices: list[NormalizedInvoice]) -> DuplicateDetectionResult:
    """
    Detect invoices that share the same LR number.

    Repeated LR numbers are flagged as potential duplicate billing. This does
    not assert fraud; downstream reconciliation decides how to handle the flag.

    The earliest-filed invoice in a shared-LR group is presumed the
    legitimate original and gets "duplicate_original" status. Every other
    invoice filed later against that same LR gets "potential_duplicate".
    """
    lr_index = build_lr_index(invoices)
    duplicate_lr_cases: list[DuplicateLRCase] = []
    invoice_results: list[InvoiceDuplicateResult] = []

    for lr_number in sorted(lr_index):
        grouped_invoices = lr_index[lr_number]
        invoice_ids = [invoice.raw.invoice_id for invoice in grouped_invoices]

        if len(grouped_invoices) == 1:
            invoice = grouped_invoices[0]
            invoice_results.append(
                InvoiceDuplicateResult(
                    invoice_id=invoice.raw.invoice_id,
                    lr_number=lr_number,
                    duplicate_status="unique",
                    related_invoice_ids=[],
                    reason=None,
                )
            )
            continue

        reason = (
            f"LR number {lr_number} appears on {len(grouped_invoices)} invoices "
            f"({', '.join(invoice_ids)}); the LR identifies one physical shipment"
        )
        duplicate_lr_cases.append(
            DuplicateLRCase(
                lr_number=lr_number,
                invoice_ids=invoice_ids,
                invoice_count=len(grouped_invoices),
                reason=reason,
            )
        )

        ordered_invoices = sorted(
            grouped_invoices,
            key=lambda inv: (inv.invoice_date, inv.raw.invoice_id),
        )
        original_invoice_id = ordered_invoices[0].raw.invoice_id

        for invoice in grouped_invoices:
            related_invoice_ids = [
                other.raw.invoice_id
                for other in grouped_invoices
                if other.raw.invoice_id != invoice.raw.invoice_id
            ]
            is_original = invoice.raw.invoice_id == original_invoice_id
            invoice_results.append(
                InvoiceDuplicateResult(
                    invoice_id=invoice.raw.invoice_id,
                    lr_number=lr_number,
                    duplicate_status=(
                        "duplicate_original" if is_original else "potential_duplicate"
                    ),
                    related_invoice_ids=related_invoice_ids,
                    reason=reason,
                )
            )

    invoice_results.sort(key=lambda result: result.invoice_id)
    return DuplicateDetectionResult(
        duplicate_lr_cases=duplicate_lr_cases,
        invoice_results=invoice_results,
    )
