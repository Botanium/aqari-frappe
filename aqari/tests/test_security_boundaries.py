from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestAqariSecurityBoundaries(FrappeTestCase):
    def test_active_synthetic_office_scope(self):
        from aqari.permissions import get_user_offices

        assert get_user_offices("demo.agent.a@aqari.local") == ["AQ-OFFICE-A"]
        assert get_user_offices("demo.reviewer@aqari.local") == ["AQ-OFFICE-A", "AQ-OFFICE-B"]

    def test_reviewer_is_read_only_for_ordinary_transaction(self):
        from aqari.permissions import has_permission

        transaction = SimpleNamespace(doctype="Aqari Transaction", office="AQ-OFFICE-A")
        user = "demo.reviewer@aqari.local"
        assert has_permission(transaction, "read", user) is True
        assert has_permission(transaction, "write", user) is False

        review = SimpleNamespace(doctype="Aqari Transaction Review", office="AQ-OFFICE-A")
        assert has_permission(review, "create", user) is True
        assert has_permission(review, "write", user) is True

    def test_registration_queue_rejects_non_review_status_filter(self):
        from aqari.api import list_transactions

        frappe.set_user("demo.reviewer@aqari.local")
        with self.assertRaises(Exception):
            list_transactions(view="review", status="Approved")

    def test_transaction_review_requires_registration_role(self):
        from aqari import api

        frappe.set_user("demo.reviewer@aqari.local")
        with patch.object(api, "user_roles", return_value={"Aqari AML Reviewer"}):
            with self.assertRaises(Exception):
                api.review_transaction("AQ-TRX-2026-002", "approve", "synthetic role boundary")

    def test_state_changing_api_methods_are_post_only(self):
        from aqari import api

        expected = {
            "create_transaction",
            "update_transaction",
            "submit_transaction",
            "review_transaction",
            "create_office_application",
            "update_office_application",
            "submit_office_application",
            "review_office_application",
            "approve_or_return_office_application",
            "withdrawal",
        }
        for name in expected:
            method = getattr(api, name)
            assert frappe.allowed_http_methods_for_whitelisted_func[method] == ["POST"], name
