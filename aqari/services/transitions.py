"""Explicit transaction and withdrawal state transitions."""

from __future__ import annotations

from typing import Any

from .validation import validate_transition


TRANSACTION_TRANSITIONS: dict[str, set[str]] = {
    "Draft": {"Data Entry", "Cancelled"},
    "Data Entry": {"Review Ready", "Cancelled"},
    "Review Ready": {"Data Entry", "Presence & Signing", "Cancelled"},
    "Presence & Signing": {"Submitted", "Data Entry", "Cancelled"},
    "Submitted": {"Under Review", "Correction Required", "Rejected"},
    "Under Review": {"Correction Required", "Rejected", "Approved"},
    "Correction Required": {"Data Entry", "Review Ready", "Cancelled"},
    "Approved": {"Registration Pending", "Completed"},
    "Registration Pending": {"Completed", "Cancelled"},
    "Completed": {"Withdrawal Draft"},
    "Withdrawal Draft": {"Completed"},
    "Rejected": set(),
    "Cancelled": set(),
}

WITHDRAWAL_TRANSITIONS: dict[str, set[str]] = {
    "Draft": {"Submitted", "Cancelled"},
    "Submitted": {"Approved", "Rejected", "Correction Required"},
    "Correction Required": {"Draft", "Submitted", "Cancelled"},
    "Approved": {"Completed"},
    "Completed": set(),
    "Rejected": set(),
    "Cancelled": set(),
}


def move_transaction(doc: Any, target: str) -> str:
    validate_transition(doc.status, target, TRANSACTION_TRANSITIONS)
    doc.status = target
    return target


def move_withdrawal(doc: Any, target: str) -> str:
    validate_transition(doc.status, target, WITHDRAWAL_TRANSITIONS)
    doc.status = target
    return target
