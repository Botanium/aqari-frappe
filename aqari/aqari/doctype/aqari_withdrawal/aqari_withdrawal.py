from __future__ import annotations

import frappe
from frappe.model.document import Document

from aqari.audit import append_event
from aqari.services.transitions import WITHDRAWAL_TRANSITIONS
from aqari.services.validation import validate_transition, validate_withdrawal


class AqariWithdrawal(Document):
    def validate(self):
        self.synthetic = 1
        transaction = frappe.get_doc("Aqari Transaction", self.transaction) if self.transaction else None
        if transaction and not transaction.synthetic:
            frappe.throw("Only synthetic transactions can be linked in this preview")
        if transaction and transaction.office != self.office:
            frappe.throw("The withdrawal office must match the transaction office")
        if transaction:
            try:
                validate_withdrawal(
                    transaction_status=transaction.status,
                    title_transferred=bool(transaction.title_transferred),
                    active_session=bool(transaction.active_session),
                    withdrawal_type=self.withdrawal_type,
                    old_buyer_area=self.old_buyer_area,
                    old_buyer_shares=self.old_buyer_shares,
                    replacement_area=self.replacement_area,
                    replacement_shares=self.replacement_shares,
                )
            except ValueError as exc:
                frappe.throw(str(exc))
        if self.old_buyer and self.old_buyer == self.replacement_buyer:
            frappe.throw("The replacement buyer must be different")
        if self.old_buyer:
            old_type, old_office, old_synthetic = frappe.db.get_value(
                "Aqari Party", self.old_buyer, ["party_type", "office", "synthetic"]
            ) or (None, None, None)
            if not old_synthetic:
                frappe.throw("Only synthetic parties can be linked in this preview")
            if old_type and old_type != "Buyer":
                frappe.throw("The withdrawing party must be a buyer")
            if old_office and old_office != self.office:
                frappe.throw("The withdrawing buyer must belong to the withdrawal office")
        if self.replacement_buyer:
            new_type, new_office, new_funds, new_synthetic = frappe.db.get_value(
                "Aqari Party", self.replacement_buyer,
                ["party_type", "office", "source_of_funds", "synthetic"],
            ) or (None, None, None, None)
            if not new_synthetic:
                frappe.throw("Only synthetic parties can be linked in this preview")
            if new_type and new_type != "Buyer":
                frappe.throw("The replacement party must be a buyer")
            if new_office and new_office != self.office:
                frappe.throw("The replacement buyer must belong to the withdrawal office")
            if not new_funds:
                frappe.throw("The replacement buyer needs a source of funds")
        if self.status in {"Submitted", "Approved", "Completed"}:
            if not all((self.seller_presence_confirmed, self.old_buyer_presence_confirmed, self.replacement_presence_confirmed)):
                frappe.throw("All withdrawal parties need synthetic presence confirmation")
        if self.status == "Completed" and not self.completed_at:
            self.completed_at = frappe.utils.now_datetime()
        previous = self.get_doc_before_save() if not self.is_new() else None
        if previous and previous.status != self.status:
            try:
                validate_transition(previous.status, self.status, WITHDRAWAL_TRANSITIONS)
            except ValueError as exc:
                frappe.throw(str(exc))

    def on_update(self):
        previous = self.get_doc_before_save() if not self.is_new() else None
        append_event(
            action="withdrawal.transition" if previous and previous.status != self.status else "withdrawal.update",
            record_type=self.doctype,
            record_name=self.name,
            office=self.office,
            reason=self.reason,
            metadata={"transaction": self.transaction, "status": self.status, "version": self.version},
        )

    def on_trash(self):
        frappe.throw("Withdrawals are never deleted", frappe.PermissionError)
