from unittest import TestCase

from aqari.services.transitions import (
    TRANSACTION_TRANSITIONS,
    WITHDRAWAL_TRANSITIONS,
)
from aqari.services.validation import validate_transition


class TestTransitions(TestCase):
    def test_allowed_transaction_transitions(self):
        for current, target in (
            ("Draft", "Data Entry"),
            ("Review Ready", "Presence & Signing"),
            ("Under Review", "Approved"),
            ("Completed", "Withdrawal Draft"),
        ):
            with self.subTest(current=current, target=target):
                validate_transition(current, target, TRANSACTION_TRANSITIONS)

    def test_transaction_cannot_skip_review(self):
        with self.assertRaises(ValueError):
            validate_transition("Submitted", "Approved", TRANSACTION_TRANSITIONS)

    def test_withdrawal_must_be_submitted_before_approval(self):
        with self.assertRaises(ValueError):
            validate_transition("Draft", "Approved", WITHDRAWAL_TRANSITIONS)
