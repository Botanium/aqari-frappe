from __future__ import annotations

import frappe
from frappe.model.document import Document


class AqariAuditEvent(Document):
    def validate(self):
        if not self.is_new() and not getattr(self.flags, "_aqari_audit_insert", False):
            frappe.throw("Audit events are append-only", frappe.PermissionError)
        self.synthetic = 1

    def on_update(self):
        # Frappe may run ``on_update`` after the initial insert.  The helper
        # marks that one insert explicitly; every later update remains denied.
        if getattr(self.flags, "_aqari_audit_insert", False) or getattr(self.flags, "in_insert", False):
            return
        frappe.throw("Audit events are append-only", frappe.PermissionError)

    def on_trash(self):
        frappe.throw("Audit events cannot be deleted", frappe.PermissionError)
