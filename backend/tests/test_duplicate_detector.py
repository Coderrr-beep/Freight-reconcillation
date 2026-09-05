from datetime import date

from models.invoice import Invoice
from models.normalized import NormalizedInvoice
from services.duplicate_detector import build_lr_index, detect_duplicate_lrs
from services.normalization import normalize_invoice


def _invoice(*, invoice_id: str, lr_number: str) -> NormalizedInvoice:
    return normalize_invoice(
        Invoice(
            invoice_id=invoice_id,
            lr_number=lr_number,
            transporter_name="Bharat Roadlines",
            origin="Pune",
            destination="Mumbai",
            vehicle_type="20-ton trailer",
            weight_billed_tons=10.0,
            rate_applied_per_ton=1000.0,
            fixed_charge_applied=500.0,
            total_amount=10500.0,
            invoice_date=date(2026, 6, 1),
        )
    )


class TestNoDuplicates:
    def test_unique_lrs_are_not_flagged(self) -> None:
        invoices = [
            _invoice(invoice_id="INV001", lr_number="LR100001"),
            _invoice(invoice_id="INV002", lr_number="LR100002"),
            _invoice(invoice_id="INV003", lr_number="LR100003"),
        ]

        result = detect_duplicate_lrs(invoices)

        assert result.duplicate_lr_cases == []
        assert result.potential_duplicate_count == 0
        assert all(item.duplicate_status == "unique" for item in result.invoice_results)
        assert {item.invoice_id for item in result.invoice_results} == {"INV001", "INV002", "INV003"}


class TestOneDuplicateLR:
    def test_one_duplicate_lr_flags_only_the_resubmission(self) -> None:
        invoices = [
            _invoice(invoice_id="INV001", lr_number="LR200001"),
            _invoice(invoice_id="INV002", lr_number="LR200001"),
            _invoice(invoice_id="INV003", lr_number="LR300001"),
        ]

        result = detect_duplicate_lrs(invoices)

        assert len(result.duplicate_lr_cases) == 1
        case = result.duplicate_lr_cases[0]
        assert case.lr_number == "LR200001"
        assert case.duplicate_status == "potential_duplicate"
        assert case.invoice_ids == ["INV001", "INV002"]
        assert case.invoice_count == 2
        assert "LR200001" in case.reason
        assert "INV001" in case.reason
        assert "INV002" in case.reason

        statuses = {
            item.invoice_id: item.duplicate_status
            for item in result.invoice_results
        }
        assert statuses["INV001"] == "duplicate_original"
        assert statuses["INV002"] == "potential_duplicate"
        flagged = {
            invoice_id
            for invoice_id, status in statuses.items()
            if status == "potential_duplicate"
        }
        assert flagged == {"INV002"}

        by_id = {item.invoice_id: item for item in result.invoice_results}

        assert by_id["INV001"].duplicate_status == "duplicate_original"
        assert by_id["INV001"].related_invoice_ids == ["INV002"]
        assert by_id["INV001"].reason == case.reason

        assert by_id["INV002"].duplicate_status == "potential_duplicate"
        assert by_id["INV002"].related_invoice_ids == ["INV001"]
        assert by_id["INV002"].reason == case.reason

        unique = by_id["INV003"]
        assert unique.duplicate_status == "unique"
        assert unique.related_invoice_ids == []


class TestMultipleInvoicesSameLR:
    def test_three_invoices_with_same_lr(self) -> None:
        invoices = [
            _invoice(invoice_id="INV010", lr_number="LR400001"),
            _invoice(invoice_id="INV011", lr_number="LR400001"),
            _invoice(invoice_id="INV012", lr_number="LR400001"),
        ]

        result = detect_duplicate_lrs(invoices)

        assert len(result.duplicate_lr_cases) == 1
        case = result.duplicate_lr_cases[0]
        assert case.invoice_ids == ["INV010", "INV011", "INV012"]
        assert case.invoice_count == 3
        assert result.potential_duplicate_count == 2

        by_id = {item.invoice_id: item for item in result.invoice_results}
        assert by_id["INV010"].duplicate_status == "duplicate_original"
        assert by_id["INV011"].duplicate_status == "potential_duplicate"
        assert by_id["INV012"].duplicate_status == "potential_duplicate"

        for item in result.invoice_results:
            assert item.lr_number == "LR400001"
            assert len(item.related_invoice_ids) == 2
            assert item.reason is not None


class TestLRIndex:
    def test_build_lr_index_uses_normalized_lr_numbers(self) -> None:
        invoices = [
            _invoice(invoice_id="INV001", lr_number=" lr500001 "),
            _invoice(invoice_id="INV002", lr_number="LR500001"),
        ]

        index = build_lr_index(invoices)
        result = detect_duplicate_lrs(invoices)

        assert len(index["LR500001"]) == 2
        assert len(result.duplicate_lr_cases) == 1
        assert result.duplicate_lr_cases[0].invoice_ids == ["INV001", "INV002"]

    def test_source_invoices_are_not_modified(self) -> None:
        invoices = [
            _invoice(invoice_id="INV001", lr_number=" lr600001 "),
            _invoice(invoice_id="INV002", lr_number="LR600002"),
        ]
        original_lr_values = [invoice.raw.lr_number for invoice in invoices]

        detect_duplicate_lrs(invoices)

        assert [invoice.raw.lr_number for invoice in invoices] == original_lr_values
    

def test_earliest_invoice_in_duplicate_group_marked_as_original():
    """Given two invoices sharing an LR filed on different dates, the
    earlier-dated invoice should be 'duplicate_original', not flagged."""
    from datetime import date

    from models.invoice import Invoice
    from services.normalization import normalize_invoice

    earlier = normalize_invoice(
        Invoice(
            invoice_id="INV0001",
            lr_number="LR100001",
            transporter_name="Ashok Transport Co.",
            origin="Coimbatore",
            destination="Chennai",
            vehicle_type="10-ton truck",
            weight_billed_tons=10.0,
            rate_applied_per_ton=1000.0,
            fixed_charge_applied=500.0,
            total_amount=10500.0,
            invoice_date=date(2026, 6, 1),
        )
    )
    later = normalize_invoice(
        Invoice(
            invoice_id="INV0002",
            lr_number="LR100001",
            transporter_name="Ashok Transport Co.",
            origin="Coimbatore",
            destination="Chennai",
            vehicle_type="10-ton truck",
            weight_billed_tons=10.0,
            rate_applied_per_ton=1000.0,
            fixed_charge_applied=500.0,
            total_amount=10500.0,
            invoice_date=date(2026, 6, 5),
        )
    )

    result = detect_duplicate_lrs([later, earlier])  # order in list shouldn't matter
    by_id = {r.invoice_id: r for r in result.invoice_results}

    assert by_id["INV0001"].duplicate_status == "duplicate_original"
    assert by_id["INV0002"].duplicate_status == "potential_duplicate"


def test_same_date_duplicate_group_breaks_tie_by_invoice_id():
    """If two invoices sharing an LR have the identical date, the lower
    invoice_id should deterministically be treated as the original."""
    from datetime import date

    from models.invoice import Invoice
    from services.normalization import normalize_invoice

    inv_a = normalize_invoice(
        Invoice(
            invoice_id="INV0005",
            lr_number="LR200002",
            transporter_name="Bharat Roadlines",
            origin="Ludhiana",
            destination="Delhi",
            vehicle_type="20-ton trailer",
            weight_billed_tons=5.0,
            rate_applied_per_ton=1200.0,
            fixed_charge_applied=700.0,
            total_amount=6700.0,
            invoice_date=date(2026, 6, 10),
        )
    )
    inv_b = normalize_invoice(
        Invoice(
            invoice_id="INV0009",
            lr_number="LR200002",
            transporter_name="Bharat Roadlines",
            origin="Ludhiana",
            destination="Delhi",
            vehicle_type="20-ton trailer",
            weight_billed_tons=5.0,
            rate_applied_per_ton=1200.0,
            fixed_charge_applied=700.0,
            total_amount=6700.0,
            invoice_date=date(2026, 6, 10),
        )
    )

    result = detect_duplicate_lrs([inv_b, inv_a])
    by_id = {r.invoice_id: r for r in result.invoice_results}

    assert by_id["INV0005"].duplicate_status == "duplicate_original"
    assert by_id["INV0009"].duplicate_status == "potential_duplicate"
