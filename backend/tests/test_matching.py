from datetime import date

import pytest

from models.invoice import Invoice
from models.rate_card import RateCardEntry
from services.matching import (
    FUZZY_AMBIGUITY_MARGIN,
    FUZZY_MATCH_THRESHOLD,
    match_invoice_to_rate_card,
)
from services.normalization import normalize_invoice, normalize_rate_card


def _invoice(
    *,
    invoice_id: str = "INV001",
    transporter_name: str,
    origin: str,
    destination: str,
    vehicle_type: str,
) -> object:
    return normalize_invoice(
        Invoice(
            invoice_id=invoice_id,
            lr_number="LR100001",
            transporter_name=transporter_name,
            origin=origin,
            destination=destination,
            vehicle_type=vehicle_type,
            weight_billed_tons=10.0,
            rate_applied_per_ton=1000.0,
            fixed_charge_applied=500.0,
            total_amount=10500.0,
            invoice_date=date(2026, 6, 1),
        )
    )


def _rate_card(
    *,
    rate_id: str,
    transporter: str,
    origin: str,
    destination: str,
    vehicle_type: str,
) -> object:
    return normalize_rate_card(
        RateCardEntry(
            rate_id=rate_id,
            transporter=transporter,
            origin=origin,
            destination=destination,
            vehicle_type=vehicle_type,
            rate_per_ton=1000.0,
            fixed_charge=500.0,
            acceptable_weight_variance_pct=3.0,
        )
    )


@pytest.fixture
def sample_rate_cards() -> list[object]:
    return [
        _rate_card(
            rate_id="RC001",
            transporter="Bharat Roadlines",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="20-ton trailer",
        ),
        _rate_card(
            rate_id="RC002",
            transporter="Ashok Transport Co.",
            origin="Ludhiana",
            destination="Delhi",
            vehicle_type="10-ton truck",
        ),
        _rate_card(
            rate_id="RC003",
            transporter="Speedway Carriers",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="20-ton trailer",
        ),
    ]


class TestExactMatch:
    def test_exact_match_returns_single_rate_card(self, sample_rate_cards: list[object]) -> None:
        invoice = _invoice(
            transporter_name="Bharat Roadlines",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="20-ton trailer",
        )

        result = match_invoice_to_rate_card(invoice, sample_rate_cards)

        assert result.match_status == "matched"
        assert result.match_method == "exact"
        assert result.is_reliable is True
        assert result.matched_rate_card is not None
        assert result.matched_rate_card.raw.rate_id == "RC001"
        assert result.similarity_score is None
        assert result.reason is None


class TestTransporterNameVariation:
    def test_fuzzy_match_handles_transporter_variant(self, sample_rate_cards: list[object]) -> None:
        invoice = _invoice(
            transporter_name="Bharat Road Lines",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="20-ton trailer",
        )

        result = match_invoice_to_rate_card(invoice, sample_rate_cards)

        assert result.match_status == "matched"
        assert result.match_method == "fuzzy"
        assert result.is_reliable is True
        assert result.matched_rate_card is not None
        assert result.matched_rate_card.raw.rate_id == "RC001"
        assert result.similarity_score is not None
        assert result.similarity_score >= FUZZY_MATCH_THRESHOLD


class TestUnknownTransporter:
    def test_unknown_transporter_returns_no_match(self, sample_rate_cards: list[object]) -> None:
        invoice = _invoice(
            transporter_name="Unknown Freight Corp",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="20-ton trailer",
        )

        result = match_invoice_to_rate_card(invoice, sample_rate_cards)

        assert result.match_status == "no_match"
        assert result.is_reliable is False
        assert result.matched_rate_card is None
        assert result.match_method is None
        assert result.reason is not None
        assert "threshold" in result.reason.lower()


class TestUnknownRoute:
    def test_unknown_route_returns_no_match(self, sample_rate_cards: list[object]) -> None:
        invoice = _invoice(
            transporter_name="Bharat Roadlines",
            origin="Chennai",
            destination="Kolkata",
            vehicle_type="20-ton trailer",
        )

        result = match_invoice_to_rate_card(invoice, sample_rate_cards)

        assert result.match_status == "no_match"
        assert result.is_reliable is False
        assert result.reason is not None
        assert "origin, destination, and vehicle type" in result.reason


class TestUnknownVehicleType:
    def test_unknown_vehicle_type_returns_no_match(self, sample_rate_cards: list[object]) -> None:
        invoice = _invoice(
            transporter_name="Bharat Roadlines",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="32-ton trailer",
        )

        result = match_invoice_to_rate_card(invoice, sample_rate_cards)

        assert result.match_status == "no_match"
        assert result.is_reliable is False
        assert result.reason is not None
        assert "32-ton trailer" in result.reason


class TestAmbiguousFuzzyMatch:
    def test_ambiguous_fuzzy_match_is_rejected(self) -> None:
        rate_cards = [
            _rate_card(
                rate_id="RC010",
                transporter="Speedway Carriers",
                origin="Pune",
                destination="Mumbai",
                vehicle_type="20-ton trailer",
            ),
            _rate_card(
                rate_id="RC011",
                transporter="Speedway Carrier",
                origin="Pune",
                destination="Mumbai",
                vehicle_type="20-ton trailer",
            ),
        ]
        invoice = _invoice(
            invoice_id="INV010",
            transporter_name="Speedway Carrriers",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="20-ton trailer",
        )

        result = match_invoice_to_rate_card(invoice, rate_cards)

        assert result.match_status == "no_match"
        assert result.is_reliable is False
        assert result.match_method is None
        assert result.reason is not None
        assert "Ambiguous fuzzy transporter match" in result.reason
        assert result.similarity_score is not None
        assert result.similarity_score >= FUZZY_MATCH_THRESHOLD

    def test_fuzzy_match_does_not_change_route_or_vehicle(self, sample_rate_cards: list[object]) -> None:
        invoice = _invoice(
            transporter_name="Bharat Road Lines",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="20-ton trailer",
        )

        result = match_invoice_to_rate_card(invoice, sample_rate_cards)

        assert result.match_status == "matched"
        assert result.match_method == "fuzzy"
        assert result.matched_rate_card is not None
        assert result.matched_rate_card.origin == "Pune"
        assert result.matched_rate_card.destination == "Mumbai"
        assert result.matched_rate_card.vehicle_type == "20-ton trailer"
        assert result.matched_rate_card.transporter == "Bharat Roadlines"
        assert result.matched_rate_card.raw.rate_id == "RC001"
