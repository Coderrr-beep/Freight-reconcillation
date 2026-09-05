"""Match invoices to rate card entries and dispatch records."""

from __future__ import annotations

from collections import defaultdict

from rapidfuzz import fuzz

from models.matching import MatchMethod, RateCardMatchResult
from models.normalized import NormalizedInvoice, NormalizedRateCardEntry

RouteVehicleKey = tuple[str, str, str]

FUZZY_MATCH_THRESHOLD = 85.0
FUZZY_AMBIGUITY_MARGIN = 5.0


def _route_vehicle_key(origin: str, destination: str, vehicle_type: str) -> RouteVehicleKey:
    return origin, destination, vehicle_type


def _index_rate_cards_by_route_vehicle(
    rate_cards: list[NormalizedRateCardEntry],
) -> dict[RouteVehicleKey, list[NormalizedRateCardEntry]]:
    index: dict[RouteVehicleKey, list[NormalizedRateCardEntry]] = defaultdict(list)
    for entry in rate_cards:
        key = _route_vehicle_key(entry.origin, entry.destination, entry.vehicle_type)
        index[key].append(entry)
    return index


def _score_transporter(invoice_transporter: str, rate_card_transporter: str) -> float:
    return float(fuzz.WRatio(invoice_transporter, rate_card_transporter))


def _no_match(
    invoice: NormalizedInvoice,
    *,
    reason: str,
    similarity_score: float | None = None,
) -> RateCardMatchResult:
    return RateCardMatchResult(
        invoice_id=invoice.raw.invoice_id,
        lr_number=invoice.lr_number,
        match_status="no_match",
        matched_rate_card=None,
        match_method=None,
        similarity_score=similarity_score,
        is_reliable=False,
        reason=reason,
    )


def _matched(
    invoice: NormalizedInvoice,
    rate_card: NormalizedRateCardEntry,
    *,
    match_method: MatchMethod,
    similarity_score: float | None = None,
) -> RateCardMatchResult:
    return RateCardMatchResult(
        invoice_id=invoice.raw.invoice_id,
        lr_number=invoice.lr_number,
        match_status="matched",
        matched_rate_card=rate_card,
        match_method=match_method,
        similarity_score=similarity_score,
        is_reliable=True,
        reason=None,
    )


def _find_fuzzy_transporter_match(
    invoice_transporter: str,
    candidate_transporters: list[str],
) -> tuple[str | None, float | None, str | None]:
    unique_transporters = sorted(set(candidate_transporters))
    if not unique_transporters:
        return None, None, "No transporter candidates for route and vehicle type"

    scored = [
        (transporter, _score_transporter(invoice_transporter, transporter))
        for transporter in unique_transporters
    ]
    scored.sort(key=lambda item: item[1], reverse=True)

    best_transporter, best_score = scored[0]
    if best_score < FUZZY_MATCH_THRESHOLD:
        return (
            None,
            best_score,
            f"Best transporter similarity {best_score:.1f} is below threshold "
            f"{FUZZY_MATCH_THRESHOLD:.1f}",
        )

    if len(scored) > 1:
        second_score = scored[1][1]
        if (
            second_score >= FUZZY_MATCH_THRESHOLD
            and (best_score - second_score) < FUZZY_AMBIGUITY_MARGIN
        ):
            return (
                None,
                best_score,
                "Ambiguous fuzzy transporter match: top scores "
                f"{best_score:.1f} and {second_score:.1f}",
            )

    return best_transporter, best_score, None


def match_invoice_to_rate_card(
    invoice: NormalizedInvoice,
    rate_cards: list[NormalizedRateCardEntry],
    *,
    rate_card_index: dict[RouteVehicleKey, list[NormalizedRateCardEntry]] | None = None,
) -> RateCardMatchResult:
    """
    Match one invoice to a rate-card row using exact and fuzzy transporter matching.

    Origin, destination, and vehicle type must match exactly throughout.
    """
    index = rate_card_index or _index_rate_cards_by_route_vehicle(rate_cards)
    route_key = _route_vehicle_key(invoice.origin, invoice.destination, invoice.vehicle_type)
    route_candidates = index.get(route_key, [])

    if not route_candidates:
        return _no_match(
            invoice,
            reason=(
                "No rate-card record found for origin, destination, and vehicle type "
                f"({invoice.origin} -> {invoice.destination}, {invoice.vehicle_type})"
            ),
        )

    exact_matches = [
        entry
        for entry in route_candidates
        if entry.transporter == invoice.transporter_name
    ]

    if len(exact_matches) == 1:
        return _matched(invoice, exact_matches[0], match_method="exact")

    if len(exact_matches) > 1:
        return _no_match(
            invoice,
            reason=(
                "Ambiguous exact match: multiple rate-card rows share transporter, "
                "origin, destination, and vehicle type"
            ),
        )

    matched_transporter, similarity_score, fuzzy_reason = _find_fuzzy_transporter_match(
        invoice.transporter_name,
        [entry.transporter for entry in route_candidates],
    )
    if matched_transporter is None:
        return _no_match(
            invoice,
            reason=fuzzy_reason or "No reliable transporter match found",
            similarity_score=similarity_score,
        )

    fuzzy_matches = [
        entry for entry in route_candidates if entry.transporter == matched_transporter
    ]
    if len(fuzzy_matches) == 1:
        return _matched(
            invoice,
            fuzzy_matches[0],
            match_method="fuzzy",
            similarity_score=similarity_score,
        )

    return _no_match(
        invoice,
        reason=(
            "Ambiguous fuzzy match: multiple rate-card rows share the matched "
            "transporter, origin, destination, and vehicle type"
        ),
        similarity_score=similarity_score,
    )


def match_invoices_to_rate_cards(
    invoices: list[NormalizedInvoice],
    rate_cards: list[NormalizedRateCardEntry],
) -> list[RateCardMatchResult]:
    """Match each invoice to the best available rate-card row."""
    index = _index_rate_cards_by_route_vehicle(rate_cards)
    return [
        match_invoice_to_rate_card(invoice, rate_cards, rate_card_index=index)
        for invoice in invoices
    ]
