#!/usr/bin/env python3
"""Validate that all engine input JSON files load successfully."""

from services.ingestion import DEFAULT_DATA_DIR, load_reconciliation_input


def main() -> None:
    data = load_reconciliation_input(DEFAULT_DATA_DIR)

    print("Ingestion validation passed.")
    print(f"Rate-card records : {len(data.rate_cards)}")
    print(f"Invoices          : {len(data.invoices)}")
    print(f"Dispatch records  : {len(data.dispatch_records)}")


if __name__ == "__main__":
    main()
