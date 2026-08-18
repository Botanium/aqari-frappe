from __future__ import annotations

import frappe
from frappe.model.document import Document


class AqariTransactionParticipant(Document):
    def validate(self):
        if self.party and frappe.db.exists("Aqari Party", self.party):
            party_type = frappe.db.get_value("Aqari Party", self.party, "party_type")
            if party_type and party_type != self.participant_type:
                frappe.throw("Participant type must match the linked party")
        if self.participant_type == "Buyer" and not self.source_of_funds:
            frappe.throw("Each buyer needs a source of funds")
        if self.represented and not self.representative_name:
            frappe.throw("A represented participant needs a representative name")
        if self.represented and not self.power_of_attorney_number:
            frappe.throw("A represented participant needs a power-of-attorney number")
        if any((self.fingerprint_simulated, self.signature_simulated)) and not self.synthetic:
            frappe.throw("Only synthetic presence markers are accepted")
        self.synthetic = 1
