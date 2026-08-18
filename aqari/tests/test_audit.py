import frappe
from frappe.tests.utils import FrappeTestCase


class TestAqariAudit(FrappeTestCase):
    def test_audit_event_is_append_only(self):
        from aqari.audit import append_event

        frappe.set_user("Administrator")
        name = append_event(
            action="test.audit",
            record_type="Aqari Office",
            record_name="AQ-OFFICE-A",
            office="AQ-OFFICE-A",
            reason="synthetic test",
        )
        event = frappe.get_doc("Aqari Audit Event", name)
        event.reason = "attempted mutation"
        with self.assertRaises(Exception):
            event.save(ignore_permissions=True)
