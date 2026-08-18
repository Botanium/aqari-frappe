import frappe
from frappe.tests.utils import FrappeTestCase


class TestAqariAPI(FrappeTestCase):
    def test_health_is_synthetic_and_allowlisted(self):
        from aqari.api import health

        response = health()
        assert response["ok"] is True
        assert response["app"] == "aqari"
        assert response["synthetic_only"] is True

    def test_guest_cannot_create_transaction(self):
        from aqari.api import create_transaction

        frappe.set_user("Guest")
        with self.assertRaises(Exception):
            create_transaction({"office": "AQ-OFFICE-A", "property": "AQ-PROPERTY-A"})
