from __future__ import annotations

import frappe
from frappe.model.document import Document


class AqariOffice(Document):
    def validate(self):
        if self.status == "Active" and not self.office_code:
            frappe.throw("An active office needs an office code")
        if self.contact_email and "@" not in self.contact_email:
            frappe.throw("Contact email is not valid")
        self.synthetic = 1
