from datetime import date

import pytest

from models.invoice import DispatchRecord, Invoice
from models.rate_card import RateCardEntry
from services.duplicate_detector import detect_duplicate_lrs
from services.ingestion import load_reconciliation_input
from services.matching import match_invoice_to_rate_card
from services.normalization import normalize_dispatch_record, normalize_invoice, normalize_rate_card, normalize_reconciliation_input
from services.reconciliation import reconcile_input, reconcile_invoice, reconcile_invoices


def _invoice(
    *,
    invoice_id: str,
    lr_number: str,
    transporter_name: str,
    origin: str,
    destination: str,
    vehicle_type: str,
    weight_billed_tons: float,
    rate_applied_per_ton: float,
    fixed_charge_applied: float,
    total_amount: float,
) -> object:
    return normalize_invoice(
        Invoice(
            invoice_id=invoice_id,
            lr_number=lr_number,
            transporter_name=transporter_name,
            origin=origin,
            destination=destination,
            vehicle_type=vehicle_type,
            weight_billed_tons=weight_billed_tons,
            rate_applied_per_ton=rate_applied_per_ton,
            fixed_charge_applied=fixed_charge_applied,
            total_amount=total_amount,
            invoice_date=date(2026, 6, 1),
        )
    )


def _rate_card(
    *,
    rate_id: str = "RC001",
    transporter: str = "Bharat Roadlines",
    origin: str = "Pune",
    destination: str = "Mumbai",
    vehicle_type: str = "20-ton trailer",
    rate_per_ton: float = 1000.0,
    fixed_charge: float = 500.0,
    acceptable_weight_variance_pct: float = 3.0,
) -> object:
    return normalize_rate_card(
        RateCardEntry(
            rate_id=rate_id,
            transporter=transporter,
            origin=origin,
            destination=destination,
            vehicle_type=vehicle_type,
            rate_per_ton=rate_per_ton,
            fixed_charge=fixed_charge,
            acceptable_weight_variance_pct=acceptable_weight_variance_pct,
        )
    )


def _dispatch(lr_number: str, dispatched_weight_tons: float) -> object:
    return normalize_dispatch_record(
        DispatchRecord(lr_number=lr_number, dispatched_weight_tons=dispatched_weight_tons)
    )


def _reconcile_single(
    invoice: object,
    *,
    rate_cards: list[object],
    dispatch_records: list[object],
    all_invoices: list[object] | None = None,
) -> object:
    invoices = all_invoices or [invoice]
    duplicate_results = detect_duplicate_lrs(invoices).invoice_results
    duplicate_result = next(
        item for item in duplicate_results if item.invoice_id == invoice.raw.invoice_id
    )
    dispatch_by_lr = {record.lr_number: record for record in dispatch_records}
    match_result = match_invoice_to_rate_card(invoice, rate_cards)
    return reconcile_invoice(
        invoice,
        match_result=match_result,
        duplicate_result=duplicate_result,
        dispatch_record=dispatch_by_lr.get(invoice.lr_number),
    )


@pytest.fixture
def contract_bundle() -> tuple[list[object], list[object]]:
    rate_cards = [_rate_card()]
    dispatch_records = [_dispatch("LR100001", 10.0)]
    return rate_cards, dispatch_records


class TestCleanInvoice:
    def test_auto_clears_when_all_checks_pass(self, contract_bundle: tuple[list[object], list[object]]) -> None:
        rate_cards, dispatch_records = contract_bundle
        invoice = _invoice(
            invoice_id="INV001",
            lr_number="LR100001",
            transporter_name="Bharat Roadlines",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="20-ton trailer",
            weight_billed_tons=10.0,
            rate_applied_per_ton=1000.0,
            fixed_charge_applied=500.0,
            total_amount=10500.0,
        )

        result = _reconcile_single(invoice, rate_cards=rate_cards, dispatch_records=dispatch_records)

        assert result.status == "auto_clear"
        assert result.discrepancy_type == "none"
        assert result.rupee_impact == 0.0
        assert result.matched_rate_id == "RC001"
        assert result.confidence == "high"
        assert "rate_card_match" in result.checks_performed
        assert "weight_variance_check" in result.checks_performed
        assert result.evidence.expected_amount == 10500.0


class TestRateMismatch:
    def test_flags_rate_overcharge(self, contract_bundle: tuple[list[object], list[object]]) -> None:
        rate_cards, dispatch_records = contract_bundle
        invoice = _invoice(
            invoice_id="INV002",
            lr_number="LR100001",
            transporter_name="Bharat Roadlines",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="20-ton trailer",
            weight_billed_tons=10.0,
            rate_applied_per_ton=1100.0,
            fixed_charge_applied=500.0,
            total_amount=11500.0,
        )

        result = _reconcile_single(invoice, rate_cards=rate_cards, dispatch_records=dispatch_records)

        assert result.status == "flagged"
        assert result.discrepancy_type == "rate_mismatch"
        assert result.rupee_impact == 1000.0
        assert result.evidence.rate_impact == 1000.0
        assert result.evidence.expected_amount == 10500.0


class TestWeightVariance:
    def test_flags_excess_weight_variance(self, contract_bundle: tuple[list[object], list[object]]) -> None:
        rate_cards, dispatch_records = contract_bundle
        invoice = _invoice(
            invoice_id="INV003",
            lr_number="LR100001",
            transporter_name="Bharat Roadlines",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="20-ton trailer",
            weight_billed_tons=11.0,
            rate_applied_per_ton=1000.0,
            fixed_charge_applied=500.0,
            total_amount=11500.0,
        )

        result = _reconcile_single(invoice, rate_cards=rate_cards, dispatch_records=dispatch_records)

        assert result.status == "flagged"
        assert result.discrepancy_type == "weight_variance"
        assert result.rupee_impact == 1000.0
        assert result.evidence.weight_variance_pct == pytest.approx(10.0)
        assert result.evidence.weight_impact == 1000.0

    def test_auto_clears_acceptable_weight_variance(
        self,
        contract_bundle: tuple[list[object], list[object]],
    ) -> None:
        rate_cards, dispatch_records = contract_bundle
        dispatch_records = [_dispatch("LR100002", 10.0)]
        invoice = _invoice(
            invoice_id="INV004",
            lr_number="LR100002",
            transporter_name="Bharat Roadlines",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="20-ton trailer",
            weight_billed_tons=10.2,
            rate_applied_per_ton=1000.0,
            fixed_charge_applied=500.0,
            total_amount=10700.0,
        )

        result = _reconcile_single(invoice, rate_cards=rate_cards, dispatch_records=dispatch_records)

        assert result.status == "auto_clear"
        assert result.discrepancy_type == "none"
        assert result.evidence.weight_variance_pct == pytest.approx(2.0)


class TestDuplicateBilling:
    def test_flags_duplicate_lr(self, contract_bundle: tuple[list[object], list[object]]) -> None:
        rate_cards, dispatch_records = contract_bundle
        invoice_one = _invoice(
            invoice_id="INV005A",
            lr_number="LR200001",
            transporter_name="Bharat Roadlines",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="20-ton trailer",
            weight_billed_tons=10.0,
            rate_applied_per_ton=1000.0,
            fixed_charge_applied=500.0,
            total_amount=10500.0,
        )
        invoice_two = _invoice(
            invoice_id="INV005B",
            lr_number="LR200001",
            transporter_name="Bharat Roadlines",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="20-ton trailer",
            weight_billed_tons=10.0,
            rate_applied_per_ton=1000.0,
            fixed_charge_applied=500.0,
            total_amount=10500.0,
        )
        dispatch_records = [_dispatch("LR200001", 10.0)]

        result = _reconcile_single(
            invoice_two,
            rate_cards=rate_cards,
            dispatch_records=dispatch_records,
            all_invoices=[invoice_one, invoice_two],
        )

        assert result.status == "flagged"
        assert result.discrepancy_type == "duplicate_billing"
        assert result.rupee_impact == 10500.0
        assert result.evidence.duplicate_related_invoice_ids == ["INV005A"]


class TestNoContract:
    def test_needs_human_when_no_rate_card_match(self) -> None:
        rate_cards = [_rate_card()]
        dispatch_records = [_dispatch("LR300001", 10.0)]
        invoice = _invoice(
            invoice_id="INV006",
            lr_number="LR300001",
            transporter_name="Unknown Carrier",
            origin="Chennai",
            destination="Hyderabad",
            vehicle_type="10-ton truck",
            weight_billed_tons=10.0,
            rate_applied_per_ton=1000.0,
            fixed_charge_applied=500.0,
            total_amount=10500.0,
        )

        result = _reconcile_single(invoice, rate_cards=rate_cards, dispatch_records=dispatch_records)

        assert result.status == "needs_human"
        assert result.discrepancy_type == "no_contracted_rate_found"
        assert result.matched_rate_id is None
        assert result.confidence == "low"


class TestFuzzyTransporterMatch:
    def test_auto_clears_reliable_fuzzy_transporter_match(
        self,
        contract_bundle: tuple[list[object], list[object]],
    ) -> None:
        rate_cards, dispatch_records = contract_bundle
        invoice = _invoice(
            invoice_id="INV007",
            lr_number="LR100001",
            transporter_name="Bharat Road Lines",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="20-ton trailer",
            weight_billed_tons=10.0,
            rate_applied_per_ton=1000.0,
            fixed_charge_applied=500.0,
            total_amount=10500.0,
        )

        result = _reconcile_single(invoice, rate_cards=rate_cards, dispatch_records=dispatch_records)

        assert result.status == "auto_clear"
        assert result.discrepancy_type == "none"
        assert result.confidence == "medium"
        assert result.evidence.match_method == "fuzzy"


class TestMultipleIssues:
    def test_reports_multiple_issues_without_double_counting(
        self,
        contract_bundle: tuple[list[object], list[object]],
    ) -> None:
        rate_cards, dispatch_records = contract_bundle
        invoice = _invoice(
            invoice_id="INV008",
            lr_number="LR100001",
            transporter_name="Bharat Roadlines",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="20-ton trailer",
            weight_billed_tons=11.0,
            rate_applied_per_ton=1100.0,
            fixed_charge_applied=500.0,
            total_amount=12600.0,
        )

        result = _reconcile_single(invoice, rate_cards=rate_cards, dispatch_records=dispatch_records)

        assert result.status == "flagged"
        assert result.discrepancy_type == "multiple_issues"
        assert set(result.evidence.issues_detected) == {"rate_mismatch", "weight_variance"}
        assert result.rupee_impact == 2100.0
        assert result.evidence.expected_amount == 10500.0


class TestSyntheticDataIntegration:
    def test_reconciles_all_engine_input_invoices(self) -> None:
        raw_input = load_reconciliation_input()
        normalized = normalize_reconciliation_input(raw_input)
        summary = reconcile_input(normalized)

        assert summary.total_invoices == 90
        assert summary.auto_clear + summary.flagged + summary.needs_human == 90
        assert all(result.invoice_id for result in summary.results)
        assert all(result.checks_performed for result in summary.results)
        assert all(result.explanation for result in summary.results)

    def test_duplicate_invoices_are_flagged_in_synthetic_data(self) -> None:
        raw_input = load_reconciliation_input()
        normalized = normalize_reconciliation_input(raw_input)
        summary = reconcile_input(normalized)

        duplicate_results = [
            result
            for result in summary.results
            if result.discrepancy_type in {"duplicate_billing", "multiple_issues"}
            and "duplicate_billing" in result.evidence.issues_detected
        ]
        assert len(duplicate_results) >= 4

    def test_no_contract_cases_need_human_review(self) -> None:
        raw_input = load_reconciliation_input()
        normalized = normalize_reconciliation_input(raw_input)
        summary = reconcile_input(normalized)

        no_contract = [
            result for result in summary.results if result.discrepancy_type == "no_contracted_rate_found"
        ]
        assert len(no_contract) >= 1
        assert all(result.status == "needs_human" for result in no_contract)
