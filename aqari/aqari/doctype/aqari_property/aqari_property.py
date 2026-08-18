from __future__ import annotations

import frappe
from frappe.model.document import Document

from aqari.services.validation import non_negative, positive


class AqariProperty(Document):
    def validate(self):
        positive(self.total_area, "Total area")
        if self.total_deed_shares:
            positive(self.total_deed_shares, "Total deed shares")
        if self.frontage is not None:
            non_negative(self.frontage, "Frontage")
        if self.depth is not None:
            non_negative(self.depth, "Depth")
        if not self.synthetic:
            frappe.throw("Only synthetic properties are accepted in this preview")
        self.synthetic = 1
