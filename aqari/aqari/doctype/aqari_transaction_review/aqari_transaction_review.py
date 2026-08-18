from __future__ import annotations

import frappe
from frappe.model.document import Document

from aqari.audit import append_event


class AqariTransactionReview(Document):
    def validate(self):
        self.synthetic = 1
        transaction_office, transaction_synthetic = frappe.db.get_value(
            "Aqari Transaction", self.transaction, ["office", "synthetic"]
        ) or (None, None)
        if not transaction_synthetic:
            frappe.throw("Only synthetic transactions can be reviewed in this preview")
        if transaction_office and transaction_office != self.office:
            frappe.throw("The review office must match the transaction office")
        if self.decision != "Pending" and not self.reason:
            frappe.throw("A review decision needs a reason")
        if self.decision != "Pending" and not self.reviewed_at:
            self.reviewed_at = frappe.utils.now_datetime()

    def on_update(self):
        if self.decision != "Pending":
            append_event(
                action="transaction.review",
                record_type=self.doctype,
                record_name=self.name,
                office=self.office,
                reason=self.reason,
                metadata={"transaction": self.transaction, "decision": self.decision},
                actor_user=self.reviewer_user,
                actor_role=self.reviewer_role,
            )

    def on_trash(self):
        frappe.throw("Review decisions are append-only", frappe.PermissionError)
