from __future__ import annotations

import frappe
from frappe.model.document import Document


class AqariParty(Document):
    def validate(self):
        if not self.full_name or len(self.full_name.strip()) < 2:
            frappe.throw("A party needs a name")
        if self.party_type == "Buyer" and not self.source_of_funds:
            frappe.throw("A buyer needs a source of funds")
        if self.national_number and not self.synthetic:
            frappe.throw("Only synthetic identity references are accepted in this preview")
        self.synthetic = 1
