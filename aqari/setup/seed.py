"""Idempotent deterministic synthetic seed for local and preview benches.

Run with ``bench --site <site> execute aqari.setup.seed.seed_demo``.  Every
record is explicitly synthetic and uses stable names so a second run does not
duplicate data.  This module never reads or imports real KYC, deed, payment,
or biometric data.
"""

from __future__ import annotations

from typing import Any

import frappe

from aqari.audit import append_event


SYNTHETIC_USERS = {
    "demo.agent.a@aqari.local": ("Demo Agent A", ["Aqari Office Agent"]),
    "demo.agent.b@aqari.local": ("Demo Agent B", ["Aqari Office Agent"]),
    "demo.reviewer@aqari.local": ("Demo Reviewer", ["Aqari Registration Reviewer"]),
    # A dedicated synthetic preview integration identity. It has both roles
    # only so one server-side credential can demonstrate the office and review
    # surfaces; production users remain individually authenticated.
    "demo.portal@aqari.local": (
        "Demo Portal Integration",
        ["Aqari Office Agent", "Aqari Registration Reviewer"],
    ),
}


def _ensure_role(role: str) -> None:
    if not frappe.db.exists("Role", role):
        frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
            ignore_permissions=True
        )


def _ensure_user(email: str, full_name: str, roles: list[str]) -> str:
    _ensure_role("Aqari Office Administrator")
    _ensure_role("Aqari Office Agent")
    _ensure_role("Aqari Registration Reviewer")
    if not frappe.db.exists("User", email):
        frappe.get_doc(
            {
                "doctype": "User",
                "name": email,
                "email": email,
                "first_name": full_name.split(" ", 1)[0],
                "full_name": full_name,
                "enabled": 1,
                "send_welcome_email": 0,
                "user_type": "System User",
            }
        ).insert(ignore_permissions=True)
    user = frappe.get_doc("User", email)
    existing_roles = {row.role for row in user.roles}
    for role in roles:
        if role not in existing_roles:
            user.add_roles(role)
    return email


def _ensure(doctype: str, identity: str | dict[str, Any], values: dict[str, Any]):
    """Return an existing synthetic record or insert it once.

    Frappe replaces supplied names for hash, field-based, and naming-series
    DocTypes.  Seed idempotency must therefore use stable business fields
    rather than assuming the requested ``name`` survives autonaming.
    """
    existing = frappe.db.exists(doctype, identity)
    if existing:
        return frappe.get_doc(doctype, existing)
    payload = {"doctype": doctype, **values}
    if isinstance(identity, str):
        payload["name"] = identity
    doc = frappe.get_doc(payload)
    doc.flags.synthetic_seed = True
    doc.insert(ignore_permissions=True)
    return doc


def _membership(name: str, office: str, user: str, role: str):
    return _ensure(
        "Aqari Office Membership",
        {"office": office, "user": user, "role": role},
        {
            "office": office,
            "user": user,
            "role": role,
            "status": "Active",
            "joined_on": "2026-01-01",
            "purpose": "Synthetic preview access",
            "synthetic": 1,
        },
    )


def _party(name: str, office: str, party_type: str, full_name: str, source_of_funds: str = ""):
    synthetic_number = f"SYN-{name}"
    return _ensure(
        "Aqari Party",
        {"office": office, "national_number": synthetic_number},
        {
            "office": office,
            "party_type": party_type,
            "full_name": full_name,
            "national_number": synthetic_number,
            "date_of_birth": "1985-05-15",
            "nationality": "Synthetic Iraqi",
            "phone": "+964000000000",
            "address": "Synthetic address, Baghdad",
            "source_of_funds": source_of_funds,
            "identity_front_reference": f"synthetic://{name}/front",
            "identity_back_reference": f"synthetic://{name}/back",
            "portrait_reference": f"synthetic://{name}/portrait",
            "synthetic": 1,
        },
    )


def _property(name: str, office: str, deed_number: str):
    return _ensure(
        "Aqari Property",
        {"office": office, "title_deed_number": deed_number},
        {
            "office": office,
            "title_deed_number": deed_number,
            "property_type": "House",
            "total_area": 120,
            "total_deed_shares": 12,
            "governorate": "Baghdad",
            "administrative_division": "Karkh",
            "area_name": "Synthetic District",
            "plot_number": "SYN-001",
            "district_number": "SYN-D1",
            "frontage": 10,
            "depth": 12,
            "registration_directorate": "Synthetic Directorate",
            "map_location": "synthetic://map/001",
            "description": "Synthetic preview property; not a legal deed.",
            "title_status": "Synthetic",
            "deed_reference": f"synthetic://{name}/deed",
            "synthetic": 1,
        },
    )


def _transaction(name: str, office: str, property_name: str, seller: str, buyer: str, status: str):
    return _ensure(
        "Aqari Transaction",
        {
            "office": office,
            "property": property_name,
            "status": status,
            "synthetic": 1,
        },
        {
            "naming_series": "AQ-TRX-.YYYY.-",
            "office": office,
            "property": property_name,
            "transaction_type": "Sale",
            "sale_scope": "Full Sale",
            "party_mode": "Single Party",
            "status": status,
            "intended_transfer_area": 120,
            "intended_transfer_shares": 12,
            "agreed_value": 250000000,
            "currency": "IQD",
            "earnest_amount": 25000000,
            "payment_percentage": 100,
            "payment_timing": "Synthetic on registration",
            "registration_trigger": "Synthetic review approval",
            "seller_default_penalty": 1000000,
            "buyer_default_penalty": 1000000,
            "optional_terms": "Synthetic terms only.",
            "bank_deposit_status": "Pending Preview",
            "title_transferred": 0,
            "active_session": 0,
            "version": 1,
            "participants": [
                {
                    "participant_type": "Seller",
                    "party": seller,
                    "owned_area": 120,
                    "owned_shares": 12,
                    "allocation_area": 120,
                    "allocation_shares": 12,
                    "portion_type": "Common Share",
                    "presence_confirmed": 1,
                    "fingerprint_simulated": 1,
                    "signature_simulated": 1,
                },
                {
                    "participant_type": "Buyer",
                    "party": buyer,
                    "allocation_area": 120,
                    "allocation_shares": 12,
                    "allocation_percentage": 100,
                    "portion_type": "Common Share",
                    "source_of_funds": "Salary",
                    "presence_confirmed": 1,
                    "fingerprint_simulated": 1,
                    "signature_simulated": 1,
                },
            ],
            "synthetic": 1,
        },
    )


def seed_demo(*, commit: bool = True) -> dict[str, Any]:
    """Create the stable two-office synthetic preview dataset."""
    from aqari.setup.install import ensure_roles

    ensure_roles()
    for email, (full_name, roles) in SYNTHETIC_USERS.items():
        _ensure_user(email, full_name, roles)

    _ensure(
        "Aqari Office",
        "AQ-OFFICE-A",
        {
            "office_code": "AQ-OFFICE-A",
            "office_name": "Aqari Synthetic Office A",
            "legal_name": "Aqari Synthetic Office A LLC",
            "status": "Active",
            "registration_number": "SYN-REG-A",
            "governorate": "Baghdad",
            "district": "Karkh",
            "address": "Synthetic office address A",
            "contact_phone": "+964000000001",
            "contact_email": "office.a@aqari.local",
            "office_admin_user": "demo.agent.a@aqari.local",
            "synthetic": 1,
        },
    )
    _ensure(
        "Aqari Office",
        "AQ-OFFICE-B",
        {
            "office_code": "AQ-OFFICE-B",
            "office_name": "Aqari Synthetic Office B",
            "legal_name": "Aqari Synthetic Office B LLC",
            "status": "Active",
            "registration_number": "SYN-REG-B",
            "governorate": "Baghdad",
            "district": "Rusafa",
            "address": "Synthetic office address B",
            "contact_phone": "+964000000002",
            "contact_email": "office.b@aqari.local",
            "office_admin_user": "demo.agent.b@aqari.local",
            "synthetic": 1,
        },
    )
    _membership("AQ-MEM-A-AGENT", "AQ-OFFICE-A", "demo.agent.a@aqari.local", "Aqari Office Agent")
    _membership("AQ-MEM-B-AGENT", "AQ-OFFICE-B", "demo.agent.b@aqari.local", "Aqari Office Agent")
    _membership("AQ-MEM-A-REVIEWER", "AQ-OFFICE-A", "demo.reviewer@aqari.local", "Aqari Registration Reviewer")
    _membership("AQ-MEM-B-REVIEWER", "AQ-OFFICE-B", "demo.reviewer@aqari.local", "Aqari Registration Reviewer")
    _membership("AQ-MEM-A-PORTAL-AGENT", "AQ-OFFICE-A", "demo.portal@aqari.local", "Aqari Office Agent")
    _membership("AQ-MEM-A-PORTAL-REVIEWER", "AQ-OFFICE-A", "demo.portal@aqari.local", "Aqari Registration Reviewer")
    _membership("AQ-MEM-B-PORTAL-REVIEWER", "AQ-OFFICE-B", "demo.portal@aqari.local", "Aqari Registration Reviewer")

    seller_a = _party("AQ-PARTY-A-SELLER", "AQ-OFFICE-A", "Seller", "Synthetic Seller A")
    buyer_a_old = _party("AQ-PARTY-A-BUYER-OLD", "AQ-OFFICE-A", "Buyer", "Synthetic Buyer A Old", "Salary")
    _party("AQ-PARTY-A-BUYER-NEW", "AQ-OFFICE-A", "Buyer", "Synthetic Buyer A New", "Investment")
    seller_b = _party("AQ-PARTY-B-SELLER", "AQ-OFFICE-B", "Seller", "Synthetic Seller B")
    buyer_b = _party("AQ-PARTY-B-BUYER", "AQ-OFFICE-B", "Buyer", "Synthetic Buyer B", "Commercial Income")

    property_a = _property("AQ-PROPERTY-A", "AQ-OFFICE-A", "SYN-DEED-A-001")
    property_b = _property("AQ-PROPERTY-B", "AQ-OFFICE-B", "SYN-DEED-B-001")
    transaction_a_completed = _transaction(
        "AQ-TRX-2026-001",
        "AQ-OFFICE-A",
        property_a.name,
        seller_a.name,
        buyer_a_old.name,
        "Completed",
    )
    transaction_a_review = _transaction(
        "AQ-TRX-2026-002",
        "AQ-OFFICE-A",
        property_a.name,
        seller_a.name,
        buyer_a_old.name,
        "Under Review",
    )
    transaction_b_entry = _transaction(
        "AQ-TRX-2026-003",
        "AQ-OFFICE-B",
        property_b.name,
        seller_b.name,
        buyer_b.name,
        "Data Entry",
    )

    if not frappe.db.exists(
        "Aqari Audit Event",
        {"record_name": transaction_a_completed.name, "action": "synthetic.seed"},
    ):
        append_event(
            action="synthetic.seed",
            record_type="Aqari Transaction",
            record_name=transaction_a_completed.name,
            office="AQ-OFFICE-A",
            reason="Deterministic synthetic preview seed",
            metadata={"dataset": "aqari-demo-v1"},
            actor_user="Administrator",
            actor_role="System Manager",
        )
    if commit:
        frappe.db.commit()
    return {
        "synthetic": True,
        "dataset": "aqari-demo-v1",
        "offices": ["AQ-OFFICE-A", "AQ-OFFICE-B"],
        "transactions": [
            transaction_a_completed.name,
            transaction_a_review.name,
            transaction_b_entry.name,
        ],
        "users": sorted(SYNTHETIC_USERS),
    }


def seed_demo_data(*, commit: bool = True) -> dict[str, Any]:
    """Compatibility alias used by some bench setup scripts."""
    return seed_demo(commit=commit)
