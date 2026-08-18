from __future__ import annotations

import frappe
from frappe.model.document import Document

from aqari.audit import append_event
from aqari.services.transitions import TRANSACTION_TRANSITIONS
from aqari.services.validation import decimal, percentage, validate_transaction_participants


class AqariTransaction(Document):
    def validate(self):
        self.synthetic = 1
        if not self.office or not self.property:
            frappe.throw("A transaction needs an office and property")
        property_office, property_synthetic = frappe.db.get_value(
            "Aqari Property", self.property, ["office", "synthetic"]
        ) or (None, None)
        if not property_synthetic:
            frappe.throw("Only synthetic properties can be linked in this preview")
        if property_office and property_office != self.office:
            frappe.throw("The property must belong to the transaction office")
        for row in self.participants:
            party_office, party_synthetic = frappe.db.get_value(
                "Aqari Party", row.party, ["office", "synthetic"]
            ) or (None, None)
            if not party_synthetic:
                frappe.throw("Only synthetic parties can be linked in this preview")
            if party_office and party_office != self.office:
                frappe.throw("Every participant must belong to the transaction office")
        previous = self.get_doc_before_save() if not self.is_new() else None
        if previous and previous.status != self.status:
            from aqari.services.validation import validate_transition

            try:
                validate_transition(previous.status, self.status, TRANSACTION_TRANSITIONS)
            except ValueError as exc:
                frappe.throw(str(exc))
            if self.status in {"Correction Required", "Rejected", "Approved"} and not getattr(self.flags, "transition_reason", None):
                frappe.throw("A review transition needs a reason")
        if self.status not in {"Draft", "Data Entry", "Correction Required"}:
            try:
                property_total_area = frappe.db.get_value("Aqari Property", self.property, "total_area") or 0
                property_total_shares = frappe.db.get_value("Aqari Property", self.property, "total_deed_shares") or 0
                validate_transaction_participants(
                    self.participants,
                    sale_scope=self.sale_scope,
                    total_area=property_total_area,
                    total_shares=property_total_shares,
                    transfer_area=self.intended_transfer_area,
                    transfer_shares=self.intended_transfer_shares,
                )
                target_area = decimal(self.intended_transfer_area, default=0)
                target_shares = decimal(self.intended_transfer_shares, default=0)
                if target_area <= 0 and target_shares <= 0:
                    buyers = [row for row in self.participants if row.participant_type == "Buyer"]
                    has_area = any(decimal(row.allocation_area, default=0) > 0 for row in buyers)
                    has_shares = any(decimal(row.allocation_shares, default=0) > 0 for row in buyers)
                    target_area = decimal(property_total_area, default=0) if has_area else 0
                    target_shares = decimal(property_total_shares, default=0) if has_shares else 0
                    if target_area <= 0 and target_shares <= 0:
                        target_area = decimal(property_total_area, default=0)
                        target_shares = decimal(property_total_shares, default=0)
                for row in self.participants:
                    if row.participant_type != "Buyer":
                        continue
                    if target_area > 0 and decimal(row.allocation_area, default=0) > 0:
                        row.allocation_percentage = float(percentage(row.allocation_area, target_area))
                    elif target_shares > 0 and decimal(row.allocation_shares, default=0) > 0:
                        row.allocation_percentage = float(percentage(row.allocation_shares, target_shares))
            except ValueError as exc:
                frappe.throw(str(exc))
        if self.status in {"Submitted", "Under Review", "Approved", "Completed"}:
            missing = [row.idx for row in self.participants if not row.presence_confirmed]
            if missing and self.status in {"Submitted", "Under Review", "Approved", "Completed"}:
                frappe.throw("Every participant needs synthetic presence confirmation")
        if self.status == "Completed" and not self.completed_at:
            self.completed_at = frappe.utils.now_datetime()

    def on_update(self):
        previous = self.get_doc_before_save() if not self.is_new() else None
        append_event(
            action="transaction.transition" if previous and previous.status != self.status else "transaction.update",
            record_type=self.doctype,
            record_name=self.name,
            office=self.office,
            reason=getattr(self.flags, "transition_reason", None),
            metadata={"status": self.status, "version": self.version},
        )

    def on_trash(self):
        frappe.throw("Transactions are never deleted; cancel or correct them instead", frappe.PermissionError)
