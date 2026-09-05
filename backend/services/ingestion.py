"""Load rate card, invoices, and dispatch records from JSON input files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from models.input import ReconciliationInput
from models.invoice import DispatchRecord, Invoice
from models.rate_card import RateCardEntry

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

RATE_CARD_FILENAME = "rate_card.json"
INVOICES_FILENAME = "invoices_for_engine.json"
DISPATCH_FILENAME = "dispatch_records.json"

ENGINE_INPUT_FILES = (
    RATE_CARD_FILENAME,
    INVOICES_FILENAME,
    DISPATCH_FILENAME,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


class IngestionError(Exception):
    """Base class for data ingestion failures."""


class MissingFileError(IngestionError):
    """Raised when a required input file does not exist."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"Required input file not found: {path}")


class FileReadError(IngestionError):
    """Raised when an input file cannot be read."""

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Failed to read {path}: {reason}")


class MalformedJsonError(IngestionError):
    """Raised when a file contains invalid JSON."""

    def __init__(self, path: Path, message: str, line: int | None = None, column: int | None = None) -> None:
        self.path = path
        self.line = line
        self.column = column
        location = ""
        if line is not None and column is not None:
            location = f" at line {line}, column {column}"
        super().__init__(f"Malformed JSON in {path}{location}: {message}")


class InvalidStructureError(IngestionError):
    """Raised when JSON decodes but does not match the expected top-level shape."""

    def __init__(self, path: Path, expected: str, actual: str) -> None:
        self.path = path
        self.expected = expected
        self.actual = actual
        super().__init__(f"Invalid structure in {path}: expected {expected}, got {actual}")


class RecordValidationError(IngestionError):
    """Raised when one or more records fail Pydantic validation."""

    def __init__(self, source: str, path: Path, failures: list[str]) -> None:
        self.source = source
        self.path = path
        self.failures = failures
        detail = "\n".join(f"  - {failure}" for failure in failures)
        super().__init__(f"Invalid record(s) in {source} ({path}):\n{detail}")


def _load_json_array(path: Path, source_name: str) -> list[object]:
    if not path.is_file():
        raise MissingFileError(path)

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileReadError(path, str(exc)) from exc

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise MalformedJsonError(path, exc.msg, exc.lineno, exc.colno) from exc

    if not isinstance(payload, list):
        raise InvalidStructureError(
            path,
            expected=f"{source_name} to be a JSON array",
            actual=type(payload).__name__,
        )

    return payload


def _validate_records(
    raw_records: list[object],
    model: type[ModelT],
    *,
    source: str,
    path: Path,
) -> list[ModelT]:
    validated: list[ModelT] = []
    failures: list[str] = []

    for index, record in enumerate(raw_records):
        if not isinstance(record, dict):
            failures.append(f"record[{index}]: expected object, got {type(record).__name__}")
            continue

        try:
            validated.append(model.model_validate(record))
        except ValidationError as exc:
            for error in exc.errors():
                location = ".".join(str(part) for part in error["loc"])
                failures.append(f"record[{index}].{location}: {error['msg']}")

    if failures:
        raise RecordValidationError(source, path, failures)

    return validated


def load_rate_cards(data_dir: Path | None = None) -> list[RateCardEntry]:
    """Load and validate rate card entries from rate_card.json."""
    directory = data_dir or DEFAULT_DATA_DIR
    path = directory / RATE_CARD_FILENAME
    raw_records = _load_json_array(path, RATE_CARD_FILENAME)
    return _validate_records(raw_records, RateCardEntry, source=RATE_CARD_FILENAME, path=path)


def load_invoices(data_dir: Path | None = None) -> list[Invoice]:
    """Load and validate invoices from invoices_for_engine.json."""
    directory = data_dir or DEFAULT_DATA_DIR
    path = directory / INVOICES_FILENAME
    raw_records = _load_json_array(path, INVOICES_FILENAME)
    return _validate_records(raw_records, Invoice, source=INVOICES_FILENAME, path=path)


def load_dispatch_records(data_dir: Path | None = None) -> list[DispatchRecord]:
    """Load and validate dispatch records from dispatch_records.json."""
    directory = data_dir or DEFAULT_DATA_DIR
    path = directory / DISPATCH_FILENAME
    raw_records = _load_json_array(path, DISPATCH_FILENAME)
    return _validate_records(raw_records, DispatchRecord, source=DISPATCH_FILENAME, path=path)


def load_reconciliation_input(data_dir: Path | None = None) -> ReconciliationInput:
    """
    Load all engine input files and return a typed ReconciliationInput.

    Only the three engine input files are read. invoices.json (ground truth)
    is intentionally excluded from this loader.
    """
    directory = data_dir or DEFAULT_DATA_DIR

    return ReconciliationInput(
        rate_cards=load_rate_cards(directory),
        invoices=load_invoices(directory),
        dispatch_records=load_dispatch_records(directory),
    )
