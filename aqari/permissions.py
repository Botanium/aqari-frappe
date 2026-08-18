"""Server-side office scoping for Aqari records.

The portal may choose an office in a request, but it can never grant itself
access.  These helpers are used by Frappe query-condition and has-permission
hooks as well as the named API methods.
"""

from __future__ import annotations

from typing import Any, Iterable

import frappe


OFFICE_ADMIN_ROLE = "Aqari Office Administrator"
OFFICE_AGENT_ROLE = "Aqari Office Agent"
REVIEWER_ROLES = {
    "Aqari Registration Reviewer",
    "Aqari AML Reviewer",
    "Aqari Judicial Reviewer",
    "Aqari Federation Reviewer",
}
REGISTRATION_REVIEWER_ROLE = "Aqari Registration Reviewer"
PLATFORM_ROLES = {"Aqari Platform Operator", "System Manager", "Administrator"}


def current_user(user: str | None = None) -> str:
    return user or getattr(frappe.session, "user", None) or "Guest"


def user_roles(user: str | None = None) -> set[str]:
    try:
        return set(frappe.get_roles(current_user(user)))
    except Exception:
        return set()


def is_platform_operator(user: str | None = None) -> bool:
    return bool(user_roles(user) & PLATFORM_ROLES)


def get_user_offices(user: str | None = None) -> list[str]:
    user = current_user(user)
    if is_platform_operator(user):
        rows = frappe.get_all(
            "Aqari Office",
            filters={"status": "Active", "synthetic": 1},
            fields=["name"],
        )
        return sorted({row.name for row in rows if row.name})
    rows = frappe.get_all(
        "Aqari Office Membership",
        filters={"user": user, "status": "Active", "synthetic": 1},
        fields=["office"],
    )
    memberships = sorted({row.office for row in rows if row.office})
    if not memberships:
        return []
    active_rows = frappe.get_all(
        "Aqari Office",
        filters={
            "name": ["in", memberships],
            "status": "Active",
            "synthetic": 1,
        },
        fields=["name"],
    )
    return sorted({row.name for row in active_rows if row.name})


def get_primary_office(user: str | None = None) -> str | None:
    offices = get_user_offices(user)
    return offices[0] if offices else None


def require_office_access(office: str, user: str | None = None, *, write: bool = False) -> str:
    if not office:
        frappe.throw("An office scope is required", frappe.ValidationError)
    user = current_user(user)
    if office not in get_user_offices(user):
        frappe.throw("The office is not active or is outside the preview scope", frappe.PermissionError)
    if is_platform_operator(user):
        return office
    if write and not (user_roles(user) & ({OFFICE_ADMIN_ROLE, OFFICE_AGENT_ROLE} | REVIEWER_ROLES)):
        frappe.throw("Your role cannot change this office record", frappe.PermissionError)
    return office


def office_record_query(user: str | None = None) -> str:
    """Permission query condition for the Office DocType itself."""
    offices = get_user_offices(user)
    if is_platform_operator(user):
        return "`tabAqari Office`.`status` = 'Active' AND `tabAqari Office`.`synthetic` = 1"
    if not offices:
        return "1=0"
    escaped = ", ".join(frappe.db.escape(office) for office in offices)
    return f"`tabAqari Office`.`status` = 'Active' AND `tabAqari Office`.`synthetic` = 1 AND `tabAqari Office`.`name` in ({escaped})"


def office_query(user: str | None = None) -> str:
    """Backward-compatible alias for ordinary office-scoped records."""
    return office_scoped_query(user)


def office_scoped_query(user: str | None = None) -> str:
    """Condition used for all ordinary office-scoped DocTypes.

    Frappe appends the condition to the target table; therefore the field is
    intentionally unqualified and works for Party, Property, Transaction,
    Review, Withdrawal, and Audit Event alike.
    """
    offices = get_user_offices(user)
    if is_platform_operator(user):
        return "synthetic = 1"
    if not offices:
        return "1=0"
    escaped = ", ".join(frappe.db.escape(office) for office in offices)
    return f"synthetic = 1 AND office in ({escaped})"


def office_membership_query(user: str | None = None) -> str:
    return office_scoped_query(user)


def office_application_query(user: str | None = None) -> str:
    """Applicants see their own cases; reviewers see the review queue."""
    user = current_user(user)
    if is_platform_operator(user) or user_roles(user) & REVIEWER_ROLES:
        return "synthetic = 1"
    return f"synthetic = 1 AND applicant_user = {frappe.db.escape(user)}"


def has_permission(doc: Any, ptype: str = "read", user: str | None = None) -> bool:
    user = current_user(user)
    if is_platform_operator(user):
        return True
    if not doc:
        if ptype in {"read", "select", "report"}:
            return bool(get_user_offices(user))
        if ptype == "create" and "Aqari Office Applicant" in user_roles(user):
            return True
        return False

    if getattr(doc, "doctype", None) == "Aqari Office Application":
        if bool(user_roles(user) & REVIEWER_ROLES):
            return ptype in {"read", "select", "report"}
        if getattr(doc, "applicant_user", None) != user:
            return False
        if ptype in {"read", "select", "report"}:
            return True
        return ptype in {"write", "create"} and getattr(doc, "status", None) in {"Draft", "Correction Required"}

    office = getattr(doc, "office", None)
    if not office and getattr(doc, "doctype", None) == "Aqari Office":
        office = getattr(doc, "name", None)
    if office not in get_user_offices(user):
        return False

    roles = user_roles(user)
    if ptype in {"read", "select", "report", "share", "email"}:
        return True
    if doc.doctype == "Aqari Audit Event":
        return False
    if doc.doctype == "Aqari Transaction Review":
        if ptype in {"write", "create", "submit", "amend"}:
            return bool(roles & REVIEWER_ROLES)
        return False
    if ptype in {"write", "create", "submit", "amend"}:
        return bool(roles & {OFFICE_ADMIN_ROLE, OFFICE_AGENT_ROLE})
    if ptype in {"delete", "cancel"}:
        return False
    return False


def can_review(user: str | None = None) -> bool:
    return is_platform_operator(user) or bool(user_roles(user) & REVIEWER_ROLES)


def can_review_transaction(user: str | None = None) -> bool:
    """Whether the current user can act on the registration review queue.

    Other authority roles may eventually receive their own review categories;
    they must not approve a registration transaction through this endpoint.
    """
    return is_platform_operator(user) or REGISTRATION_REVIEWER_ROLE in user_roles(user)


def can_edit_transaction(doc: Any, user: str | None = None) -> bool:
    if is_platform_operator(user):
        return True
    if not has_permission(doc, "write", user):
        return False
    return getattr(doc, "status", None) in {"Draft", "Data Entry", "Correction Required", "Review Ready"}


def ensure_safe_office_payload(payload: dict[str, Any], user: str | None = None) -> str:
    requested = payload.get("office")
    if requested:
        return require_office_access(requested, user)
    primary = get_primary_office(user)
    if not primary:
        frappe.throw("The current user has no active Aqari office", frappe.PermissionError)
    return primary
