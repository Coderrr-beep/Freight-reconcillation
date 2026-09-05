from datetime import date

import pytest

from models.invoice import DispatchRecord, Invoice
from models.rate_card import RateCardEntry
from services.normalization import (
    normalize_date,
    normalize_dispatch_record,
    normalize_invoice,
    normalize_monetary_value,
    normalize_numeric,
    normalize_rate_card,
    normalize_route,
    normalize_transporter_name,
    normalize_vehicle_type,
    normalize_weight,
    strip_legal_suffixes,
)


class TestTransporterNameNormalization:
    def test_strips_common_legal_suffixes(self) -> None:
        assert normalize_transporter_name("ABC Logistics Pvt Ltd") == "Abc Logistics"
        assert normalize_transporter_name("ABC Logistics Private Limited") == "Abc Logistics"
        assert normalize_transporter_name("ABC Logistics") == "Abc Logistics"

    def test_normalizes_casing_whitespace_and_punctuation(self) -> None:
        assert normalize_transporter_name("  BHARAT ROADLINES  ") == "Bharat Roadlines"
        assert normalize_transporter_name("Ashok Transport Co.") == "Ashok Transport"
        assert normalize_transporter_name("Speedway Carriers Pvt. Ltd.") == "Speedway Carriers"

    def test_does_not_fuzzy_match_variants(self) -> None:
        assert normalize_transporter_name("Bharat Road Lines") != normalize_transporter_name(
            "Bharat Roadlines"
        )
        assert normalize_transporter_name("Sri Balaji Log.") != normalize_transporter_name(
            "Sri Balaji Logistics"
        )


class TestRouteNormalization:
    def test_normalizes_origin_and_destination(self) -> None:
        assert normalize_route("  delhi  ") == "Delhi"
        assert normalize_route("BENGALURU") == "Bengaluru"
        assert normalize_route(" Coimbatore , ") == "Coimbatore"


class TestVehicleTypeNormalization:
    def test_normalizes_casing_whitespace_and_hyphens(self) -> None:
        assert normalize_vehicle_type("  20-TON TRAILER  ") == "20-ton trailer"
        assert normalize_vehicle_type("10 - ton truck") == "10-ton truck"
        assert normalize_vehicle_type("32-ton trailer") == "32-ton trailer"


class TestNumericNormalization:
    def test_coerces_string_numbers(self) -> None:
        assert normalize_numeric("1302.79") == 1302.79
        assert normalize_numeric("1,234.50") == 1234.5

    def test_normalizes_monetary_and_weight_precision(self) -> None:
        assert normalize_monetary_value(5358.809) == 5358.81
        assert normalize_weight(3.111) == 3.11

    def test_rejects_empty_numeric_strings(self) -> None:
        with pytest.raises(ValueError, match="Numeric value cannot be empty"):
            normalize_numeric("   ")


class TestDateNormalization:
    def test_normalizes_date_object_and_string(self) -> None:
        parsed, iso_value = normalize_date(date(2026, 7, 11))
        assert parsed == date(2026, 7, 11)
        assert iso_value == "2026-07-11"

        parsed_from_str, iso_from_str = normalize_date(" 2026-06-01 ")
        assert parsed_from_str == date(2026, 6, 1)
        assert iso_from_str == "2026-06-01"


class TestRecordNormalizationPreservesRawValues:
    def test_normalize_invoice_preserves_raw_record(self) -> None:
        raw = Invoice(
            invoice_id="INV0081",
            lr_number=" lr172792 ",
            transporter_name="Bharat Roadlines Pvt Ltd",
            origin=" pune ",
            destination="MUMBAI",
            vehicle_type=" 20 - ton trailer ",
            weight_billed_tons=7.18,
            rate_applied_per_ton=1283.01,
            fixed_charge_applied=1204.57,
            total_amount=10416.58,
            invoice_date=date(2026, 6, 23),
        )

        normalized = normalize_invoice(raw)

        assert normalized.raw is raw
        assert normalized.raw.transporter_name == "Bharat Roadlines Pvt Ltd"
        assert normalized.transporter_name == "Bharat Roadlines"
        assert normalized.origin == "Pune"
        assert normalized.destination == "Mumbai"
        assert normalized.vehicle_type == "20-ton trailer"
        assert normalized.lr_number == "LR172792"
        assert normalized.invoice_date_iso == "2026-06-23"

    def test_normalize_rate_card_preserves_raw_record(self) -> None:
        raw = RateCardEntry(
            rate_id="RC008",
            transporter="Ashok Transport Co.",
            origin="ludhiana",
            destination="delhi",
            vehicle_type="10-TON TRUCK",
            rate_per_ton=1270.93,
            fixed_charge=1216.02,
            acceptable_weight_variance_pct=3.0,
        )

        normalized = normalize_rate_card(raw)

        assert normalized.raw is raw
        assert normalized.raw.transporter == "Ashok Transport Co."
        assert normalized.transporter == "Ashok Transport"
        assert normalized.origin == "Ludhiana"
        assert normalized.destination == "Delhi"
        assert normalized.vehicle_type == "10-ton truck"

    def test_normalize_dispatch_record_preserves_raw_record(self) -> None:
        raw = DispatchRecord(lr_number=" lr167136 ", dispatched_weight_tons=6.72)

        normalized = normalize_dispatch_record(raw)

        assert normalized.raw is raw
        assert normalized.raw.lr_number == " lr167136 "
        assert normalized.lr_number == "LR167136"
        assert normalized.dispatched_weight_tons == 6.72


class TestSuffixStripping:
    def test_strips_suffixes_iteratively(self) -> None:
        assert strip_legal_suffixes("National Freight Movers Pvt Ltd") == "National Freight Movers"
