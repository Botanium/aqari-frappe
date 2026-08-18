"""Pure domain validation helpers for the synthetic Aqari workflow.

These helpers deliberately do not know about SQL or HTTP.  Controllers and API
methods supply Frappe documents and translate ``ValueError`` into Frappe
validation/permission errors at the boundary.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable, Mapping


AREA_QUANTUM = Decimal("0.0001")
PERCENT_QUANTUM = Decimal("0.01")


def decimal(value: Any, *, default: Decimal | None = None) -> Decimal:
    if value in (None, ""):
        if default is not None:
            return default
        raise ValueError("A numeric value is required")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid numeric value: {value!r}") from exc


def quantize(value: Decimal, quantum: Decimal = AREA_QUANTUM) -> Decimal:
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def positive(value: Any, label: str) -> Decimal:
    parsed = decimal(value)
    if parsed <= 0:
        raise ValueError(f"{label} must be greater than zero")
    return parsed


def non_negative(value: Any, label: str) -> Decimal:
    parsed = decimal(value, default=Decimal("0"))
    if parsed < 0:
        raise ValueError(f"{label} cannot be negative")
    return parsed


def percentage(part: Any, total: Any) -> Decimal:
    part_value = decimal(part, default=Decimal("0"))
    total_value = positive(total, "total")
    if part_value < 0 or part_value > total_value:
        raise ValueError("The allocated amount must be within the total")
    return quantize((part_value / total_value) * Decimal("100"), PERCENT_QUANTUM)


def _value(row: Mapping[str, Any] | Any, key: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(key, default)
    return getattr(row, key, default)


def _rows(rows: Iterable[Mapping[str, Any] | Any]) -> list[Mapping[str, Any] | Any]:
    return list(rows or [])


def reconcile_allocations(
    rows: Iterable[Mapping[str, Any] | Any],
    *,
    target_area: Any = None,
    target_shares: Any = None,
    label: str = "allocation",
) -> dict[str, Decimal]:
    """Validate seller/buyer allocations and return deterministic totals.

    At least one unit (square metres or deed shares) must be supplied.  When
    both units are present, both are checked independently.  Percentages are
    derived from the target, so callers never have to trust client-calculated
    percentages.
    """

    material_rows = _rows(rows)
    if not material_rows:
        raise ValueError(f"At least one {label} row is required")
    area_target = decimal(target_area, default=Decimal("0"))
    share_target = decimal(target_shares, default=Decimal("0"))
    if area_target <= 0 and share_target <= 0:
        raise ValueError("A positive area or deed-share target is required")

    area_total = Decimal("0")
    share_total = Decimal("0")
    percentages: list[Decimal] = []
    for index, row in enumerate(material_rows, start=1):
        area = non_negative(_value(row, "allocation_area", 0), f"{label} {index} area")
        shares = non_negative(_value(row, "allocation_shares", 0), f"{label} {index} shares")
        if area <= 0 and shares <= 0:
            raise ValueError(f"{label} {index} needs an area or deed-share allocation")
        area_total += area
        share_total += shares
        if area_target > 0 and share_target > 0 and area > 0 and shares > 0:
            area_percentage = percentage(area, area_target)
            share_percentage = percentage(shares, share_target)
            if abs(area_percentage - share_percentage) > PERCENT_QUANTUM:
                raise ValueError(f"{label} {index} area and deed-share percentages differ")
        basis = area_target if area_target > 0 else share_target
        amount = area if area_target > 0 else shares
        percentages.append(percentage(amount, basis))

    if area_target > 0 and quantize(area_total) != quantize(area_target):
        raise ValueError(f"{label} area must reconcile to {area_target}")
    if share_target > 0 and quantize(share_total, Decimal("0.000001")) != quantize(
        share_target, Decimal("0.000001")
    ):
        raise ValueError(f"{label} deed shares must reconcile to {share_target}")
    if quantize(sum(percentages), PERCENT_QUANTUM) != Decimal("100.00"):
        raise ValueError(f"{label} percentages must reconcile to 100")
    return {
        "area": quantize(area_total),
        "shares": quantize(share_total, Decimal("0.000001")),
        "percentage": Decimal("100.00"),
    }


def validate_transaction_participants(
    participants: Iterable[Mapping[str, Any] | Any],
    *,
    sale_scope: str,
    total_area: Any,
    total_shares: Any,
    transfer_area: Any = None,
    transfer_shares: Any = None,
) -> dict[str, Decimal]:
    rows = _rows(participants)
    sellers = [row for row in rows if _value(row, "participant_type") == "Seller"]
    buyers = [row for row in rows if _value(row, "participant_type") == "Buyer"]
    if not sellers:
        raise ValueError("At least one seller participant is required")
    if not buyers:
        raise ValueError("At least one buyer participant is required")

    total_area_value = non_negative(total_area, "property total area")
    total_shares_value = non_negative(total_shares, "property total deed shares")
    target_area = decimal(transfer_area, default=Decimal("0"))
    target_shares = decimal(transfer_shares, default=Decimal("0"))
    if sale_scope == "Full Sale":
        # If the caller supplies one unit explicitly, validate that unit only.
        # When neither is supplied, a full sale defaults to both deed totals.
        if target_area <= 0 and target_shares <= 0:
            buyers = [row for row in rows if _value(row, "participant_type") == "Buyer"]
            buyer_has_area = any(decimal(_value(row, "allocation_area", 0), default=Decimal("0")) > 0 for row in buyers)
            buyer_has_shares = any(decimal(_value(row, "allocation_shares", 0), default=Decimal("0")) > 0 for row in buyers)
            if buyer_has_area and total_area_value > 0:
                target_area = total_area_value
            if buyer_has_shares and total_shares_value > 0:
                target_shares = total_shares_value
            if target_area <= 0 and target_shares <= 0:
                if total_area_value > 0:
                    target_area = total_area_value
                if total_shares_value > 0:
                    target_shares = total_shares_value
    elif sale_scope == "Partial Sale":
        if target_area <= 0 and target_shares <= 0:
            raise ValueError("A partial sale needs a positive transfer area or deed shares")
    else:
        raise ValueError("Sale scope must be Full Sale or Partial Sale")

    seller_owned_area = sum(
        (non_negative(_value(row, "owned_area", 0), "seller owned area") for row in sellers),
        Decimal("0"),
    )
    seller_owned_shares = sum(
        (non_negative(_value(row, "owned_shares", 0), "seller owned shares") for row in sellers),
        Decimal("0"),
    )
    if target_area > 0 and seller_owned_area > 0 and seller_owned_area < target_area:
        raise ValueError("Transferred area exceeds seller ownership")
    if target_shares > 0 and seller_owned_shares > 0 and seller_owned_shares < target_shares:
        raise ValueError("Transferred deed shares exceed seller ownership")

    buyer_totals = reconcile_allocations(
        buyers,
        target_area=target_area,
        target_shares=target_shares,
        label="buyer allocation",
    )
    if sale_scope == "Partial Sale":
        boundaries = [
            "north_boundary",
            "south_boundary",
            "east_boundary",
            "west_boundary",
        ]
        separated = any(_value(row, "portion_type") == "Separated Portion" for row in rows)
        if separated and any(not str(_value(row, field, "")).strip() for field in boundaries for row in rows):
            raise ValueError("Separated portions require all four boundaries")
    return buyer_totals


def validate_transition(current: str, target: str, transitions: Mapping[str, set[str]]) -> None:
    allowed = transitions.get(current, set())
    if target not in allowed:
        raise ValueError(f"Transition {current!r} -> {target!r} is not allowed")


def validate_withdrawal(
    *,
    transaction_status: str,
    title_transferred: bool,
    active_session: bool,
    withdrawal_type: str,
    old_buyer_area: Any = None,
    old_buyer_shares: Any = None,
    replacement_area: Any = None,
    replacement_shares: Any = None,
) -> dict[str, Decimal]:
    if transaction_status != "Completed":
        raise ValueError("Only completed transactions can be withdrawn")
    if title_transferred:
        raise ValueError("A transaction with transferred title is not withdrawable")
    if active_session:
        raise ValueError("An active transaction session blocks withdrawal")
    if withdrawal_type not in {"Full Withdrawal", "Partial Withdrawal"}:
        raise ValueError("Withdrawal type must be Full Withdrawal or Partial Withdrawal")
    old_area = positive(old_buyer_area, "old buyer area") if old_buyer_area not in (None, "") else Decimal("0")
    old_shares = positive(old_buyer_shares, "old buyer shares") if old_buyer_shares not in (None, "") else Decimal("0")
    replacement_area_value = positive(replacement_area, "replacement area") if replacement_area not in (None, "") else Decimal("0")
    replacement_shares_value = positive(replacement_shares, "replacement deed shares") if replacement_shares not in (None, "") else Decimal("0")
    if replacement_area_value <= 0 and replacement_shares_value <= 0:
        raise ValueError("A replacement needs an area or deed-share amount")
    if old_area > 0 and replacement_area_value > old_area:
        raise ValueError("Replacement area exceeds the withdrawing buyer's allocation")
    if old_shares > 0 and replacement_shares_value > old_shares:
        raise ValueError("Replacement deed shares exceed the withdrawing buyer's allocation")
    if withdrawal_type == "Full Withdrawal":
        if old_area > 0 and replacement_area_value != old_area:
            raise ValueError("Full withdrawal must replace the old buyer's full area")
        if old_shares > 0 and replacement_shares_value != old_shares:
            raise ValueError("Full withdrawal must replace the old buyer's full shares")
    return {"area": quantize(replacement_area_value), "shares": quantize(replacement_shares_value, Decimal("0.000001"))}
