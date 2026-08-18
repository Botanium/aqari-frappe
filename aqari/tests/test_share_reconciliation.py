from decimal import Decimal
from unittest import TestCase

from aqari.services.validation import (
    reconcile_allocations,
    validate_transaction_participants,
    validate_withdrawal,
)


class TestShareReconciliation(TestCase):
    def test_buyer_allocations_reconcile_area_and_shares(self):
        result = reconcile_allocations(
            [
                {"allocation_area": 60, "allocation_shares": 6},
                {"allocation_area": 60, "allocation_shares": 6},
            ],
            target_area=120,
            target_shares=12,
        )
        self.assertEqual(result["area"], Decimal("120.0000"))
        self.assertEqual(result["shares"], Decimal("12.000000"))
        self.assertEqual(result["percentage"], Decimal("100.00"))

    def test_partial_sale_rejects_allocation_above_seller_ownership(self):
        with self.assertRaisesRegex(ValueError, "exceeds seller ownership"):
            validate_transaction_participants(
                [
                    {"participant_type": "Seller", "owned_area": 50, "owned_shares": 5},
                    {"participant_type": "Buyer", "allocation_area": 60, "allocation_shares": 6},
                ],
                sale_scope="Partial Sale",
                total_area=100,
                total_shares=10,
                transfer_area=60,
                transfer_shares=6,
            )

    def test_separated_portion_requires_four_boundaries(self):
        with self.assertRaisesRegex(ValueError, "four boundaries"):
            validate_transaction_participants(
                [
                    {"participant_type": "Seller", "owned_area": 50, "owned_shares": 5, "portion_type": "Separated Portion"},
                    {"participant_type": "Buyer", "allocation_area": 50, "allocation_shares": 5, "portion_type": "Separated Portion"},
                ],
                sale_scope="Partial Sale",
                total_area=100,
                total_shares=10,
                transfer_area=50,
                transfer_shares=5,
            )

    def test_partial_withdrawal_cannot_replace_more_than_old_allocation(self):
        with self.assertRaisesRegex(ValueError, "exceeds"):
            validate_withdrawal(
                transaction_status="Completed",
                title_transferred=False,
                active_session=False,
                withdrawal_type="Partial Withdrawal",
                old_buyer_area=40,
                replacement_area=41,
            )
