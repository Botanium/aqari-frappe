import frappe
from frappe.tests.utils import FrappeTestCase


class TestAqariOfficeIsolation(FrappeTestCase):
    def test_office_query_has_no_rows_without_membership(self):
        from aqari.permissions import office_scoped_query

        frappe.set_user("Guest")
        assert office_scoped_query("Guest") == "1=0"

    def test_agent_cannot_read_other_office(self):
        from aqari.permissions import has_permission

        frappe.set_user("demo.agent.a@aqari.local")
        other_office = frappe.get_doc("Aqari Office", "AQ-OFFICE-B")
        assert has_permission(other_office, "read", frappe.session.user) is False
