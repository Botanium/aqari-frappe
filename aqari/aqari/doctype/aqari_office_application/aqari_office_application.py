from __future__ import annotations

import frappe
from frappe.model.document import Document

from aqari.audit import append_event
from aqari.services.validation import validate_transition


APPLICATION_TRANSITIONS = {
    "Draft": {"Submitted"},
    "Submitted": {"Under Review"},
    "Under Review": {"Correction Required", "Approved", "Rejected"},
    "Correction Required": {"Draft", "Submitted"},
    "Approved": set(),
    "Rejected": set(),
}


class AqariOfficeApplication(Document):
    def validate(self):
        self.synthetic = 1
        for field in ("applicant_user", "office_name", "governorate", "address", "contact_phone", "contact_email"):
            if not str(self.get(field) or "").strip():
                frappe.throw(f"{field.replace('_', ' ').title()} is required")
        if "@" not in self.contact_email:
            frappe.throw("Contact email is not valid")
        previous = self.get_doc_before_save() if not self.is_new() else None
        if previous and previous.status != self.status:
            try:
                validate_transition(previous.status, self.status, APPLICATION_TRANSITIONS)
            except ValueError as exc:
                frappe.throw(str(exc))
        if self.status in {"Approved", "Rejected", "Correction Required"} and not self.decision_reason:
            frappe.throw("A reviewed application needs a decision reason")

    def on_update(self):
        append_event(
            action="office_application.update",
            record_type=self.doctype,
            record_name=self.name,
            office=self.approved_office,
            reason=self.decision_reason,
            metadata={"status": self.status, "applicant_user": self.applicant_user},
        )

    def on_trash(self):
        frappe.throw("Office applications are retained for audit", frappe.PermissionError)
