from __future__ import annotations

import frappe
from frappe.model.document import Document


class AqariOfficeMembership(Document):
    def validate(self):
        if self.status == "Inactive" and self.left_on and self.joined_on and self.left_on < self.joined_on:
            frappe.throw("Left On cannot be before Joined On")
        if self.office and frappe.db.exists("Aqari Office", self.office):
            office_status = frappe.db.get_value("Aqari Office", self.office, "status")
            if office_status == "Revoked" and self.status == "Active":
                frappe.throw("A revoked office cannot receive an active membership")
        self.synthetic = 1
