"""Install-time setup for Aqari's explicit least-privilege roles."""

from __future__ import annotations

import frappe


AQARI_ROLES = (
    "Aqari Office Applicant",
    "Aqari Office Administrator",
    "Aqari Office Agent",
    "Aqari Registration Reviewer",
    "Aqari AML Reviewer",
    "Aqari Judicial Reviewer",
    "Aqari Federation Reviewer",
    "Aqari Platform Operator",
    "Aqari Security Auditor",
)


def ensure_roles() -> None:
    for role in AQARI_ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
                ignore_permissions=True
            )


def after_install() -> None:
    ensure_roles()
