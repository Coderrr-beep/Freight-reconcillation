"""
Synthetic data generator for the Freight Invoice Reconciliation Agent.

Generates THREE data sources (this is what makes it "multi-source
reconciliation" rather than a single-table check):

  1. rate_card.json          : the contract — what SHOULD be charged
  2. invoices_for_engine.json: what the transporter actually billed
  3. dispatch_records.json   : the weighbridge/dispatch note — the
                                independent record of actual shipped weight,
                                used to catch weight-billing discrepancies
                                that the rate card alone can't reveal

  invoices.json (WITH ground_truth) is also written — this is the answer
  key, used only by the scoring module, never fed to the engine.

Run: python3 scripts/generate_synthetic_data.py
Outputs land in ./data/
"""

import json
import random
import os
from datetime import datetime, timedelta

random.seed(42)  # reproducible dataset — important for demoing consistent numbers

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(OUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# 1. RATE CARD — the ground truth contract data
# ---------------------------------------------------------------------------

TRANSPORTERS = [
    "Ashok Transport Co.",
    "Bharat Roadlines",
    "Sri Balaji Logistics",
    "Speedway Carriers",
    "National Freight Movers",
]

TRANSPORTER_VARIANTS = {
    "Ashok Transport Co.": ["Ashok Transport", "Ashok Transport Company", "ASHOK TRANSPORT CO"],
    "Bharat Roadlines": ["Bharat Road Lines", "Bharat Roadlines Pvt Ltd", "BHARAT ROADLINES"],
    "Sri Balaji Logistics": ["Sri Balaji Logistic", "S. Balaji Logistics", "Sri Balaji Log."],
    "Speedway Carriers": ["Speedway Carrier", "Speedway Carriers Pvt. Ltd.", "Speedway Carriers Ltd"],
    "National Freight Movers": ["National Freight Mover", "Natl. Freight Movers", "National Freight Movers Pvt Ltd"],
}

ROUTES = [
    ("Coimbatore", "Chennai"),
    ("Coimbatore", "Bengaluru"),
    ("Ludhiana", "Delhi"),
    ("Rajkot", "Ahmedabad"),
    ("Ahmedabad", "Mumbai"),
    ("Chennai", "Hyderabad"),
    ("Pune", "Mumbai"),
    ("Delhi", "Jaipur"),
]

VEHICLE_TYPES = ["10-ton truck", "16-ton truck", "20-ton trailer", "32-ton trailer"]


def build_rate_card():
    rate_card = []
    rid = 1
    for transporter in TRANSPORTERS:
        serviced_routes = random.sample(ROUTES, k=random.randint(4, 6))
        for origin, dest in serviced_routes:
            vehicle = random.choice(VEHICLE_TYPES)
            rate_card.append({
                "rate_id": f"RC{rid:03d}",
                "transporter": transporter,
                "origin": origin,
                "destination": dest,
                "vehicle_type": vehicle,
                "rate_per_ton": round(random.uniform(850, 1600), 2),
                "fixed_charge": round(random.uniform(500, 1500), 2),
                "acceptable_weight_variance_pct": 3.0,  # contract tolerance
            })
            rid += 1
    return rate_card


# ---------------------------------------------------------------------------
# 2. INVOICE + DISPATCH RECORD GENERATION
#    Each generator returns (invoice_dict, dispatch_weight_or_None)
#    dispatch_weight is the "actual" weighbridge-measured weight for that LR.
# ---------------------------------------------------------------------------

def random_date():
    start = datetime(2026, 6, 1)
    return (start + timedelta(days=random.randint(0, 60))).strftime("%Y-%m-%d")


def make_clean_invoice(inv_id, rate_row):
    weight = round(random.uniform(3, 18), 2)
    amount = round(weight * rate_row["rate_per_ton"] + rate_row["fixed_charge"], 2)
    lr = f"LR{random.randint(100000, 999999)}"
    invoice = {
        "invoice_id": inv_id,
        "lr_number": lr,
        "transporter_name": rate_row["transporter"],
        "origin": rate_row["origin"],
        "destination": rate_row["destination"],
        "vehicle_type": rate_row["vehicle_type"],
        "weight_billed_tons": weight,
        "rate_applied_per_ton": rate_row["rate_per_ton"],
        "fixed_charge_applied": rate_row["fixed_charge"],
        "total_amount": amount,
        "invoice_date": random_date(),
        "ground_truth": {
            "is_discrepancy": False,
            "type": "clean",
            "expected_action": "auto_clear",
            "rupee_impact": 0.0,
        },
    }
    dispatch_weight = weight  # matches exactly — no variance
    return invoice, dispatch_weight


def make_rate_mismatch_invoice(inv_id, rate_row):
    weight = round(random.uniform(3, 18), 2)
    overcharge_pct = random.uniform(0.06, 0.22)
    billed_rate = round(rate_row["rate_per_ton"] * (1 + overcharge_pct), 2)
    amount = round(weight * billed_rate + rate_row["fixed_charge"], 2)
    correct_amount = round(weight * rate_row["rate_per_ton"] + rate_row["fixed_charge"], 2)
    lr = f"LR{random.randint(100000, 999999)}"
    invoice = {
        "invoice_id": inv_id,
        "lr_number": lr,
        "transporter_name": rate_row["transporter"],
        "origin": rate_row["origin"],
        "destination": rate_row["destination"],
        "vehicle_type": rate_row["vehicle_type"],
        "weight_billed_tons": weight,
        "rate_applied_per_ton": billed_rate,
        "fixed_charge_applied": rate_row["fixed_charge"],
        "total_amount": amount,
        "invoice_date": random_date(),
        "ground_truth": {
            "is_discrepancy": True,
            "type": "rate_mismatch",
            "expected_action": "flag",
            "rupee_impact": round(amount - correct_amount, 2),
        },
    }
    dispatch_weight = weight  # weight itself is fine, only the rate is wrong
    return invoice, dispatch_weight


def make_weight_variance_invoice(inv_id, rate_row, within_tolerance):
    """
    dispatch_weight = the REAL weighbridge-measured weight (independent source)
    weight_billed   = what the transporter invoiced (may differ)
    """
    dispatch_weight = round(random.uniform(3, 18), 2)
    if within_tolerance:
        variance_pct = random.uniform(0.5, 2.5)   # inside 3% contract tolerance
    else:
        variance_pct = random.uniform(6, 15)       # clearly outside tolerance
    billed_weight = round(dispatch_weight * (1 + variance_pct / 100), 2)
    amount = round(billed_weight * rate_row["rate_per_ton"] + rate_row["fixed_charge"], 2)
    correct_amount = round(dispatch_weight * rate_row["rate_per_ton"] + rate_row["fixed_charge"], 2)
    lr = f"LR{random.randint(100000, 999999)}"
    invoice = {
        "invoice_id": inv_id,
        "lr_number": lr,
        "transporter_name": rate_row["transporter"],
        "origin": rate_row["origin"],
        "destination": rate_row["destination"],
        "vehicle_type": rate_row["vehicle_type"],
        "weight_billed_tons": billed_weight,
        "rate_applied_per_ton": rate_row["rate_per_ton"],
        "fixed_charge_applied": rate_row["fixed_charge"],
        "total_amount": amount,
        "invoice_date": random_date(),
        "ground_truth": {
            "is_discrepancy": not within_tolerance,
            "type": "weight_variance_acceptable" if within_tolerance else "weight_variance_excess",
            "expected_action": "auto_clear" if within_tolerance else "flag",
            "rupee_impact": 0.0 if within_tolerance else round(amount - correct_amount, 2),
        },
    }
    return invoice, dispatch_weight


def make_duplicate_invoice(inv_id, source_invoice):
    """Same LR billed twice — no new dispatch record needed, LR already has one."""
    dup = dict(source_invoice)
    dup["invoice_id"] = inv_id
    dup["invoice_date"] = random_date()
    dup["ground_truth"] = {
        "is_discrepancy": True,
        "type": "duplicate_billing",
        "expected_action": "flag",
        "rupee_impact": source_invoice["total_amount"],
    }
    return dup  # no dispatch_weight returned — reuses the original LR's record


def make_name_variant_invoice(inv_id, rate_row):
    weight = round(random.uniform(3, 18), 2)
    amount = round(weight * rate_row["rate_per_ton"] + rate_row["fixed_charge"], 2)
    lr = f"LR{random.randint(100000, 999999)}"
    variant_name = random.choice(TRANSPORTER_VARIANTS[rate_row["transporter"]])
    invoice = {
        "invoice_id": inv_id,
        "lr_number": lr,
        "transporter_name": variant_name,
        "origin": rate_row["origin"],
        "destination": rate_row["destination"],
        "vehicle_type": rate_row["vehicle_type"],
        "weight_billed_tons": weight,
        "rate_applied_per_ton": rate_row["rate_per_ton"],
        "fixed_charge_applied": rate_row["fixed_charge"],
        "total_amount": amount,
        "invoice_date": random_date(),
        "ground_truth": {
            "is_discrepancy": False,
            "type": "transporter_name_variant",
            "expected_action": "auto_clear_after_fuzzy_match",
            "rupee_impact": 0.0,
        },
    }
    dispatch_weight = weight
    return invoice, dispatch_weight


def make_ambiguous_invoice(inv_id, transporter):
    origin, dest = random.choice(ROUTES)
    weight = round(random.uniform(3, 18), 2)
    guess_rate = round(random.uniform(900, 1500), 2)
    amount = round(weight * guess_rate + random.uniform(500, 1000), 2)
    lr = f"LR{random.randint(100000, 999999)}"
    invoice = {
        "invoice_id": inv_id,
        "lr_number": lr,
        "transporter_name": transporter,
        "origin": origin,
        "destination": dest,
        "vehicle_type": random.choice(VEHICLE_TYPES),
        "weight_billed_tons": weight,
        "rate_applied_per_ton": guess_rate,
        "fixed_charge_applied": round(amount - weight * guess_rate, 2),
        "total_amount": amount,
        "invoice_date": random_date(),
        "ground_truth": {
            "is_discrepancy": None,
            "type": "no_contracted_rate_found",
            "expected_action": "needs_human",
            "rupee_impact": None,
        },
    }
    dispatch_weight = weight  # weight itself isn't the issue here, the rate is unknown
    return invoice, dispatch_weight


def generate_invoices(rate_card, total=90):
    invoices = []
    dispatch_records = {}  # lr_number -> dispatched_weight_tons
    inv_counter = 1

    def next_id():
        nonlocal inv_counter
        iid = f"INV{inv_counter:04d}"
        inv_counter += 1
        return iid

    n_clean = int(total * 0.60)
    n_rate_mismatch = int(total * 0.15)
    n_weight_variance = int(total * 0.10)
    n_duplicate = int(total * 0.05)
    n_name_variant = int(total * 0.05)
    n_ambiguous = total - (n_clean + n_rate_mismatch + n_weight_variance + n_duplicate + n_name_variant)

    for _ in range(n_clean):
        rate_row = random.choice(rate_card)
        inv, dw = make_clean_invoice(next_id(), rate_row)
        invoices.append(inv)
        dispatch_records[inv["lr_number"]] = dw

    for _ in range(n_rate_mismatch):
        rate_row = random.choice(rate_card)
        inv, dw = make_rate_mismatch_invoice(next_id(), rate_row)
        invoices.append(inv)
        dispatch_records[inv["lr_number"]] = dw

    for i in range(n_weight_variance):
        rate_row = random.choice(rate_card)
        within = i % 2 == 0
        inv, dw = make_weight_variance_invoice(next_id(), rate_row, within)
        invoices.append(inv)
        dispatch_records[inv["lr_number"]] = dw

    clean_invoices = [inv for inv in invoices if inv["ground_truth"]["type"] == "clean"]
    for _ in range(n_duplicate):
        source = random.choice(clean_invoices)
        dup = make_duplicate_invoice(next_id(), source)
        invoices.append(dup)
        # no new dispatch record — same LR as source, one physical shipment

    for _ in range(n_name_variant):
        rate_row = random.choice(rate_card)
        inv, dw = make_name_variant_invoice(next_id(), rate_row)
        invoices.append(inv)
        dispatch_records[inv["lr_number"]] = dw

    for _ in range(n_ambiguous):
        transporter = random.choice(TRANSPORTERS)
        inv, dw = make_ambiguous_invoice(next_id(), transporter)
        invoices.append(inv)
        dispatch_records[inv["lr_number"]] = dw

    random.shuffle(invoices)
    return invoices, dispatch_records


def main():
    rate_card = build_rate_card()
    invoices, dispatch_records = generate_invoices(rate_card, total=90)

    with open(os.path.join(OUT_DIR, "rate_card.json"), "w") as f:
        json.dump(rate_card, f, indent=2)

    with open(os.path.join(OUT_DIR, "invoices.json"), "w") as f:
        json.dump(invoices, f, indent=2)

    invoices_no_gt = [{k: v for k, v in inv.items() if k != "ground_truth"} for inv in invoices]
    with open(os.path.join(OUT_DIR, "invoices_for_engine.json"), "w") as f:
        json.dump(invoices_no_gt, f, indent=2)

    dispatch_list = [
        {"lr_number": lr, "dispatched_weight_tons": w}
        for lr, w in sorted(dispatch_records.items())
    ]
    with open(os.path.join(OUT_DIR, "dispatch_records.json"), "w") as f:
        json.dump(dispatch_list, f, indent=2)

    type_counts = {}
    for inv in invoices:
        t = inv["ground_truth"]["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    print(f"Rate card rows: {len(rate_card)}")
    print(f"Invoices generated: {len(invoices)}")
    print(f"Dispatch records (unique LRs): {len(dispatch_list)}")
    print("Distribution:")
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c}")
    print(f"\nFiles written to {OUT_DIR}/")
    print("  - rate_card.json              (contracted rates — source 1)")
    print("  - invoices_for_engine.json    (billed invoices — source 2, feed this to the engine)")
    print("  - dispatch_records.json       (weighbridge actuals — source 3, feed this to the engine)")
    print("  - invoices.json               (invoices WITH ground_truth — answer key, scoring only)")


if __name__ == "__main__":
    main()
