"""Named, allowlisted API for the Aqari portal.

Every method below is intentionally explicit.  There is no generic DocType,
resource, SQL, or method proxy.  Payloads are narrowed before they reach a
Frappe document and every office/role check runs on the server.
"""

from __future__ import annotations

import json
from typing import Any

import frappe

from aqari.audit import append_event
from aqari.permissions import (
    can_edit_transaction,
    can_review,
    can_review_transaction,
    current_user,
    ensure_safe_office_payload,
    get_primary_office,
    get_user_offices,
    is_platform_operator,
    has_permission,
    require_office_access,
    user_roles,
)
from aqari.aqari.doctype.aqari_office_application.aqari_office_application import (
    APPLICATION_TRANSITIONS,
)
from aqari.services.validation import validate_transition
from aqari.services.transitions import move_transaction, move_withdrawal


TRANSACTION_FIELDS = {
    "office",
    "property",
    "transaction_type",
    "sale_scope",
    "party_mode",
    "status",
    "intended_transfer_area",
    "intended_transfer_shares",
    "agreed_value",
    "currency",
    "earnest_amount",
    "payment_percentage",
    "payment_timing",
    "registration_trigger",
    "seller_default_penalty",
    "buyer_default_penalty",
    "optional_terms",
    "bank_deposit_status",
    "participants",
}
PARTICIPANT_FIELDS = {
    "participant_type",
    "party",
    "owned_area",
    "owned_shares",
    "allocation_area",
    "allocation_shares",
    "portion_type",
    "north_boundary",
    "south_boundary",
    "east_boundary",
    "west_boundary",
    "represented",
    "representative_name",
    "power_of_attorney_number",
    "power_of_attorney_date",
    "source_of_funds",
}
WITHDRAWAL_FIELDS = {
    "transaction",
    "office",
    "withdrawal_type",
    "old_buyer",
    "old_buyer_area",
    "old_buyer_shares",
    "replacement_buyer",
    "replacement_area",
    "replacement_shares",
    "reason",
}
OFFICE_APPLICATION_FIELDS = {
    "office_name",
    "legal_name",
    "governorate",
    "district",
    "address",
    "contact_phone",
    "contact_email",
    "registration_reference",
}
PROPERTY_FIELDS = {
    "title_deed_number",
    "property_type",
    "total_area",
    "total_deed_shares",
    "governorate",
    "administrative_division",
    "area_name",
    "plot_number",
    "district_number",
    "frontage",
    "depth",
    "registration_directorate",
    "map_location",
    "description",
    "title_status",
    "deed_reference",
}
PARTY_FIELDS = {
    "party_type",
    "full_name",
    "national_number",
    "date_of_birth",
    "nationality",
    "phone",
    "address",
    "source_of_funds",
    "identity_front_reference",
    "identity_back_reference",
    "portrait_reference",
}


def _payload(value: Any, *, name: str = "payload") -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            frappe.throw(f"{name} must be valid JSON", frappe.ValidationError)
    if not isinstance(value, dict):
        frappe.throw(f"{name} must be an object", frappe.ValidationError)
    return value


def _require_user() -> str:
    user = current_user()
    if user in {"Guest", "guest", ""}:
        frappe.throw("Authentication is required", frappe.PermissionError)
    return user


def _safe_fields(source: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    return {key: value for key, value in source.items() if key in allowed}


def _is_true(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() in {"1", "true", "yes"})


def _office_for_payload(payload: dict[str, Any], user: str) -> str:
    office = ensure_safe_office_payload(payload, user)
    office = require_office_access(office, user, write=True)
    if not is_platform_operator(user) and not user_roles(user) & {
        "Aqari Office Administrator",
        "Aqari Office Agent",
    }:
        frappe.throw("An office agent role is required", frappe.PermissionError)
    return office


def _property_for_payload(data: dict[str, Any], office: str) -> str:
    property_name = data.get("property")
    if property_name:
        property_doc = frappe.get_doc("Aqari Property", property_name)
        if not property_doc.synthetic:
            frappe.throw("Only synthetic properties are accepted in this preview", frappe.PermissionError)
        if property_doc.office != office:
            frappe.throw("The property is outside the selected office", frappe.PermissionError)
        return property_doc.name

    values = _safe_fields(_payload(data.get("property_data"), name="property_data"), PROPERTY_FIELDS)
    deed_number = str(values.get("title_deed_number") or "").strip()
    if not deed_number:
        frappe.throw("A title deed number is required", frappe.ValidationError)
    existing = frappe.db.exists(
        "Aqari Property",
        {"office": office, "title_deed_number": deed_number},
    )
    if existing:
        return str(existing)
    values.update({"office": office, "synthetic": 1})
    property_doc = frappe.get_doc({"doctype": "Aqari Property", **values})
    property_doc.insert(ignore_permissions=True)
    return property_doc.name


def _party_for_participant(row: dict[str, Any], office: str) -> str:
    party_name = row.get("party")
    if party_name:
        party_doc = frappe.get_doc("Aqari Party", party_name)
        if not party_doc.synthetic:
            frappe.throw("Only synthetic parties are accepted in this preview", frappe.PermissionError)
        if party_doc.office != office:
            frappe.throw("A participant is outside the selected office", frappe.PermissionError)
        return party_doc.name

    values = _safe_fields(_payload(row.get("party_data"), name="party_data"), PARTY_FIELDS)
    values["party_type"] = values.get("party_type") or row.get("participant_type")
    full_name = str(values.get("full_name") or "").strip()
    if not full_name:
        frappe.throw("Every participant needs a full name", frappe.ValidationError)
    national_number = str(values.get("national_number") or "").strip()
    existing = None
    if national_number:
        existing = frappe.db.exists(
            "Aqari Party",
            {"office": office, "national_number": national_number},
        )
    if existing:
        return str(existing)
    values.update({"office": office, "synthetic": 1})
    party_doc = frappe.get_doc({"doctype": "Aqari Party", **values})
    party_doc.insert(ignore_permissions=True)
    return party_doc.name


def _transaction(name: str):
    if not name or not isinstance(name, str):
        frappe.throw("A transaction name is required", frappe.ValidationError)
    try:
        doc = frappe.get_doc("Aqari Transaction", name)
        if not doc.synthetic:
            frappe.throw("Only synthetic transactions are available in this preview", frappe.PermissionError)
        return doc
    except Exception:
        frappe.throw("Transaction was not found", frappe.DoesNotExistError)


def _serialize_participant(row: Any) -> dict[str, Any]:
    result = {
        "name": row.name,
        "participant_type": row.participant_type,
        "party": row.party,
        "owned_area": row.owned_area,
        "owned_shares": row.owned_shares,
        "allocation_area": row.allocation_area,
        "allocation_shares": row.allocation_shares,
        "allocation_percentage": row.allocation_percentage,
        "portion_type": row.portion_type,
        "represented": row.represented,
        "representative_name": row.representative_name,
        "power_of_attorney_number": row.power_of_attorney_number,
        "source_of_funds": row.source_of_funds,
        "presence_confirmed": row.presence_confirmed,
        "fingerprint_simulated": row.fingerprint_simulated,
        "signature_simulated": row.signature_simulated,
    }
    if row.party:
        result["full_name"] = frappe.db.get_value(
            "Aqari Party", {"name": row.party, "synthetic": 1}, "full_name"
        )
    return result


def _serialize_transaction(doc: Any, *, include_participants: bool = True) -> dict[str, Any]:
    fields = [
        "name",
        "office",
        "property",
        "transaction_type",
        "sale_scope",
        "party_mode",
        "status",
        "intended_transfer_area",
        "intended_transfer_shares",
        "agreed_value",
        "currency",
        "earnest_amount",
        "payment_percentage",
        "payment_timing",
        "registration_trigger",
        "seller_default_penalty",
        "buyer_default_penalty",
        "optional_terms",
        "bank_deposit_status",
        "title_transferred",
        "active_session",
        "version",
        "submitted_at",
        "completed_at",
    ]
    result = {field: getattr(doc, field, None) for field in fields}
    if doc.property:
        property_values = frappe.db.get_value(
            "Aqari Property",
            {"name": doc.property, "synthetic": 1},
            ["property_type", "governorate", "title_deed_number", "total_area"],
            as_dict=True,
        )
        if property_values:
            result.update(
                {
                    "property_type": property_values.property_type,
                    "governorate": property_values.governorate,
                    "deed_number": property_values.title_deed_number,
                    "total_area": property_values.total_area,
                }
            )
    if include_participants:
        result["participants"] = [_serialize_participant(row) for row in doc.participants]
    return result


TRANSACTION_PROGRESS = {
    "Draft": 12,
    "Data Entry": 24,
    "Review Ready": 40,
    "Presence & Signing": 52,
    "Submitted": 64,
    "Under Review": 72,
    "Correction Required": 46,
    "Rejected": 100,
    "Approved": 84,
    "Registration Pending": 92,
    "Completed": 100,
    "Withdrawal Draft": 30,
    "Cancelled": 100,
}

TRANSACTION_NEXT_ACTION = {
    "Draft": ("استكمال البيانات", "Complete data"),
    "Data Entry": ("استكمال البيانات", "Complete data"),
    "Review Ready": ("تأكيد الحضور والتوقيع", "Confirm presence and signing"),
    "Presence & Signing": ("إرسال للمراجعة", "Submit for review"),
    "Submitted": ("بانتظار بدء المراجعة", "Await review"),
    "Under Review": ("قيد مراجعة الجهة المختصة", "Authority review in progress"),
    "Correction Required": ("إجراء التصحيحات المطلوبة", "Apply requested corrections"),
    "Rejected": ("مراجعة قرار الرفض", "Review rejection decision"),
    "Approved": ("الإحالة إلى التسجيل العقاري", "Refer for property registration"),
    "Registration Pending": ("بانتظار اكتمال التسجيل", "Await registration completion"),
    "Completed": ("لا يوجد إجراء مطلوب", "No action required"),
    "Withdrawal Draft": ("استكمال طلب الانسحاب", "Complete withdrawal request"),
    "Cancelled": ("لا يوجد إجراء مطلوب", "No action required"),
}


def _serialize_withdrawal(doc: Any) -> dict[str, Any]:
    return {
        field: getattr(doc, field, None)
        for field in (
            "name",
            "transaction",
            "office",
            "withdrawal_type",
            "status",
            "old_buyer",
            "old_buyer_area",
            "old_buyer_shares",
            "replacement_buyer",
            "replacement_area",
            "replacement_shares",
            "reason",
            "seller_presence_confirmed",
            "old_buyer_presence_confirmed",
            "replacement_presence_confirmed",
            "fingerprint_simulated",
            "version",
            "submitted_at",
            "completed_at",
        )
    }


def _serialize_office_application(doc: Any) -> dict[str, Any]:
    return {
        field: getattr(doc, field, None)
        for field in (
            "name",
            "applicant_user",
            "office_name",
            "legal_name",
            "governorate",
            "district",
            "address",
            "contact_phone",
            "contact_email",
            "registration_reference",
            "status",
            "reviewer_user",
            "reviewer_role",
            "decision_reason",
            "submitted_at",
            "reviewed_at",
            "approved_office",
        )
    }


@frappe.whitelist(allow_guest=True)
def health() -> dict[str, Any]:
    """Unauthenticated readiness signal for the private ingress only."""
    return {
        "ok": True,
        "app": "aqari",
        "app_version": "0.1.0",
        "synthetic_only": True,
        "frappe_version": getattr(frappe, "__version__", None),
    }


@frappe.whitelist()
def session() -> dict[str, Any]:
    user = current_user()
    return {
        "authenticated": user not in {"Guest", "guest", ""},
        "user": user,
        "roles": sorted(user_roles(user)),
        "offices": get_user_offices(user),
        "primary_office": get_primary_office(user),
        "synthetic_only": True,
    }


@frappe.whitelist()
def dashboard(office: str | None = None) -> dict[str, Any]:
    user = _require_user()
    office_name = require_office_access(office, user) if office else get_primary_office(user)
    if not office_name:
        frappe.throw("The current user has no active office", frappe.PermissionError)
    rows = frappe.get_all(
        "Aqari Transaction",
        filters={"office": office_name, "synthetic": 1},
        fields=["name", "status", "transaction_type", "modified"],
        order_by="modified desc",
        limit_page_length=1000,
    )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    completed = counts.get("Completed", 0)
    correction = counts.get("Correction Required", 0)
    pending = sum(counts.get(status_name, 0) for status_name in ("Draft", "Data Entry", "Review Ready", "Presence & Signing", "Submitted", "Under Review", "Registration Pending"))
    return {
        "office": office_name,
        # Stable summary keys keep the server adapter small while the richer
        # metrics/pending payload remains available to operational surfaces.
        "total": len(rows),
        "completed": completed,
        "pending": pending,
        "correction": correction,
        "completion_rate": round((completed / len(rows)) * 100, 2) if rows else 0,
        "completionRate": round((completed / len(rows)) * 100, 2) if rows else 0,
        "metrics": {"transaction_count": len(rows), "by_status": counts},
        "pending_items": [row for row in rows if row.status in {"Draft", "Data Entry", "Correction Required", "Under Review"}][:10],
        "health": health(),
    }


@frappe.whitelist()
def list_transactions(
    office: str | None = None,
    status: str | None = None,
    transaction_type: str | None = None,
    search: str | None = None,
    view: str | None = None,
    page: int = 1,
    page_length: int = 20,
) -> dict[str, Any]:
    user = _require_user()
    review_statuses = {"Submitted", "Under Review", "Correction Required"}
    if view == "review":
        if not can_review_transaction(user):
            frappe.throw("A registration reviewer role is required", frappe.PermissionError)
        scoped_offices = get_user_offices(user)
        if not scoped_offices:
            frappe.throw("The reviewer has no assigned offices", frappe.PermissionError)
        office_name = office or ",".join(scoped_offices)
        if office:
            require_office_access(office, user)
        filters: dict[str, Any] = {
            "office": ["in", [office] if office else scoped_offices],
            "status": ["in", sorted(review_statuses)],
            "synthetic": 1,
        }
    else:
        office_name = require_office_access(office, user) if office else get_primary_office(user)
        if not office_name:
            frappe.throw("The current user has no active office", frappe.PermissionError)
        filters = {"office": office_name, "synthetic": 1}
    if view == "review" and status and status not in review_statuses:
        frappe.throw("The registration review queue only accepts submitted review statuses", frappe.ValidationError)
    if status in {"Draft", "Data Entry", "Review Ready", "Presence & Signing", "Submitted", "Under Review", "Correction Required", "Rejected", "Approved", "Registration Pending", "Completed", "Withdrawal Draft", "Cancelled"}:
        filters["status"] = status
    if transaction_type in {"Sale", "Rental"}:
        filters["transaction_type"] = transaction_type
    if search:
        filters["name"] = ["like", f"%{str(search)[:80]}%"]
    page = max(int(page or 1), 1)
    page_length = min(max(int(page_length or 20), 1), 100)
    rows = frappe.get_all(
        "Aqari Transaction",
        filters=filters,
        fields=["name", "office", "property", "transaction_type", "sale_scope", "status", "agreed_value", "currency", "creation", "modified", "submitted_at"],
        order_by="modified desc",
        limit_start=(page - 1) * page_length,
        limit_page_length=page_length,
    )
    transaction_names = [row.name for row in rows]
    property_names = sorted({row.property for row in rows if row.property})
    property_rows = (
        frappe.get_all(
            "Aqari Property",
            filters={"name": ["in", property_names], "synthetic": 1},
            fields=["name", "property_type", "governorate", "title_deed_number"],
        )
        if property_names
        else []
    )
    properties = {row.name: row for row in property_rows}
    participant_rows = (
        frappe.get_all(
            "Aqari Transaction Participant",
            filters={"parent": ["in", transaction_names], "synthetic": 1},
            fields=["parent", "participant_type", "party"],
            order_by="idx asc",
        )
        if transaction_names
        else []
    )
    party_names = sorted({row.party for row in participant_rows if row.party})
    party_rows = (
        frappe.get_all(
            "Aqari Party",
            filters={"name": ["in", party_names], "synthetic": 1},
            fields=["name", "full_name"],
        )
        if party_names
        else []
    )
    parties = {row.name: row.full_name for row in party_rows}
    participants_by_transaction: dict[str, list[Any]] = {}
    for participant in participant_rows:
        participants_by_transaction.setdefault(participant.parent, []).append(participant)

    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        property_row = properties.get(row.property)
        participants = participants_by_transaction.get(row.name, [])
        seller = next(
            (parties.get(party.party) for party in participants if party.participant_type == "Seller"),
            None,
        )
        buyer = next(
            (parties.get(party.party) for party in participants if party.participant_type == "Buyer"),
            None,
        )
        next_action, next_action_en = TRANSACTION_NEXT_ACTION.get(
            row.status,
            ("متابعة المعاملة", "Follow up"),
        )
        item.update(
            {
                "reference": row.name,
                "property_type": property_row.property_type if property_row else None,
                "governorate": property_row.governorate if property_row else None,
                "deed_number": property_row.title_deed_number if property_row else None,
                "parties_count": len(participants),
                "seller_label": seller,
                "seller_label_en": seller,
                "buyer_label": buyer,
                "buyer_label_en": buyer,
                "progress": TRANSACTION_PROGRESS.get(row.status, 0),
                "next_action": next_action,
                "next_action_en": next_action_en,
            }
        )
        items.append(item)
    return {"office": office_name, "page": page, "page_length": page_length, "items": items}


@frappe.whitelist()
def transaction_detail(name: str | None = None, transaction_id: str | None = None) -> dict[str, Any]:
    user = _require_user()
    doc = _transaction(name or transaction_id)
    require_office_access(doc.office, user)
    append_event(action="transaction.read", record_type=doc.doctype, record_name=doc.name, office=doc.office)
    return _serialize_transaction(doc)


@frappe.whitelist(methods=["POST"])
def create_transaction(payload: Any = None) -> dict[str, Any]:
    user = _require_user()
    data = _payload(payload)
    office = _office_for_payload(data, user)
    property_name = _property_for_payload(data, office)
    values = _safe_fields(data, TRANSACTION_FIELDS)
    values["office"] = office
    values["property"] = property_name
    values["status"] = "Draft"
    values["synthetic"] = 1
    participant_rows = values.pop("participants", []) or []
    if not isinstance(participant_rows, list):
        frappe.throw("participants must be a list", frappe.ValidationError)
    doc = frappe.get_doc({"doctype": "Aqari Transaction", **values})
    for row in participant_rows:
        if not isinstance(row, dict):
            frappe.throw("Each participant must be an object", frappe.ValidationError)
        party_name = _party_for_participant(row, office)
        doc.append(
            "participants",
            {**_safe_fields(row, PARTICIPANT_FIELDS), "party": party_name, "synthetic": 1},
        )
    doc.insert(ignore_permissions=True)
    append_event(action="transaction.create", record_type=doc.doctype, record_name=doc.name, office=office)
    return _serialize_transaction(doc)


@frappe.whitelist(methods=["POST"])
def update_transaction(name: str, payload: Any = None) -> dict[str, Any]:
    user = _require_user()
    doc = _transaction(name)
    require_office_access(doc.office, user)
    if not can_edit_transaction(doc, user):
        frappe.throw("This transaction is not editable in its current state", frappe.PermissionError)
    data = _payload(payload)
    values = _safe_fields(data, TRANSACTION_FIELDS - {"office"})
    participant_rows = values.pop("participants", None)
    for key, value in values.items():
        setattr(doc, key, value)
    if participant_rows is not None:
        if not isinstance(participant_rows, list):
            frappe.throw("participants must be a list", frappe.ValidationError)
        doc.set("participants", [])
        for row in participant_rows:
            if not isinstance(row, dict):
                frappe.throw("Each participant must be an object", frappe.ValidationError)
            doc.append("participants", {**_safe_fields(row, PARTICIPANT_FIELDS), "synthetic": 1})
    doc.version = int(doc.version or 1) + 1
    doc.save(ignore_permissions=True)
    append_event(action="transaction.update", record_type=doc.doctype, record_name=doc.name, office=doc.office, metadata={"version": doc.version})
    return _serialize_transaction(doc)


@frappe.whitelist(methods=["POST"])
def submit_transaction(name: str, simulate_presence: bool = False) -> dict[str, Any]:
    user = _require_user()
    doc = _transaction(name)
    require_office_access(doc.office, user)
    if not can_edit_transaction(doc, user) and doc.status not in {"Presence & Signing", "Submitted"}:
        frappe.throw("This transaction is not submittable in its current state", frappe.PermissionError)
    if doc.status == "Submitted":
        return _serialize_transaction(doc)
    if not _is_true(simulate_presence):
        frappe.throw("The preview requires explicit synthetic presence confirmation", frappe.ValidationError)
    if doc.status == "Review Ready":
        move_transaction(doc, "Presence & Signing")
        doc.flags.transition_reason = "Synthetic presence and signing started"
        doc.save(ignore_permissions=True)
    for row in doc.participants:
        row.presence_confirmed = 1
        row.fingerprint_simulated = 1
        row.signature_simulated = 1
    if doc.status == "Presence & Signing":
        move_transaction(doc, "Submitted")
    else:
        frappe.throw("Only a review-ready transaction can be submitted", frappe.ValidationError)
    doc.submitted_at = frappe.utils.now_datetime()
    doc.flags.transition_reason = "Synthetic presence and signing submitted"
    doc.save(ignore_permissions=True)
    append_event(action="transaction.submit", record_type=doc.doctype, record_name=doc.name, office=doc.office, reason="Synthetic presence and signing")
    return _serialize_transaction(doc)


@frappe.whitelist(methods=["POST"])
def review_transaction(name: str, decision: str, reason: str = "") -> dict[str, Any]:
    user = _require_user()
    if not can_review_transaction(user):
        frappe.throw("A registration reviewer role is required", frappe.PermissionError)
    doc = _transaction(name)
    require_office_access(doc.office, user)
    if doc.status == "Submitted":
        move_transaction(doc, "Under Review")
    if doc.status != "Under Review":
        frappe.throw("Only submitted transactions can be reviewed", frappe.ValidationError)
    target = {"return": "Correction Required", "Return for Correction": "Correction Required", "reject": "Rejected", "Reject": "Rejected", "approve": "Approved", "Approve": "Approved"}.get(decision)
    if not target:
        frappe.throw("Decision must be approve, reject, or return", frappe.ValidationError)
    if not reason.strip():
        frappe.throw("A review decision needs a reason", frappe.ValidationError)
    doc.flags.transition_reason = reason
    doc.save(ignore_permissions=True)
    move_transaction(doc, target)
    doc.flags.transition_reason = reason
    doc.save(ignore_permissions=True)
    reviewer_roles = sorted(user_roles(user) & {"Aqari Registration Reviewer"})
    reviewer_role = reviewer_roles[0] if reviewer_roles else "Aqari Platform Operator"
    review = frappe.get_doc(
        {
            "doctype": "Aqari Transaction Review",
            "transaction": doc.name,
            "office": doc.office,
            "reviewer_user": user,
            "reviewer_role": reviewer_role,
            "decision": {"Correction Required": "Return for Correction", "Rejected": "Reject", "Approved": "Approve"}[target],
            "reason": reason,
            "synthetic": 1,
        }
    )
    review.insert(ignore_permissions=True)
    append_event(action="transaction.review", record_type=doc.doctype, record_name=doc.name, office=doc.office, reason=reason, metadata={"decision": target})
    return {"transaction": _serialize_transaction(doc), "review": {"name": review.name, "decision": review.decision, "reason": review.reason}}


@frappe.whitelist(methods=["POST"])
def create_office_application(payload: Any = None) -> dict[str, Any]:
    user = _require_user()
    data = _payload(payload)
    values = _safe_fields(data, OFFICE_APPLICATION_FIELDS)
    values.update({"applicant_user": user, "status": "Draft", "synthetic": 1})
    doc = frappe.get_doc({"doctype": "Aqari Office Application", **values})
    doc.insert(ignore_permissions=True)
    append_event(action="office_application.create", record_type=doc.doctype, record_name=doc.name, reason="Synthetic office application")
    return _serialize_office_application(doc)


@frappe.whitelist(methods=["POST"])
def update_office_application(name: str, payload: Any = None) -> dict[str, Any]:
    user = _require_user()
    doc = frappe.get_doc("Aqari Office Application", name)
    if not is_platform_operator(user) and doc.applicant_user != user:
        frappe.throw("You cannot edit this office application", frappe.PermissionError)
    if doc.status not in {"Draft", "Correction Required"}:
        frappe.throw("Only draft or returned applications can be edited", frappe.PermissionError)
    for key, value in _safe_fields(_payload(payload), OFFICE_APPLICATION_FIELDS).items():
        setattr(doc, key, value)
    doc.save(ignore_permissions=True)
    append_event(action="office_application.update", record_type=doc.doctype, record_name=doc.name, reason="Synthetic office application update")
    return _serialize_office_application(doc)


@frappe.whitelist(methods=["POST"])
def submit_office_application(name: str) -> dict[str, Any]:
    user = _require_user()
    doc = frappe.get_doc("Aqari Office Application", name)
    if not is_platform_operator(user) and doc.applicant_user != user:
        frappe.throw("You cannot submit this office application", frappe.PermissionError)
    if doc.status not in {"Draft", "Correction Required"}:
        frappe.throw("Only draft or returned applications can be submitted", frappe.ValidationError)
    target = "Submitted"
    validate_transition(doc.status, target, APPLICATION_TRANSITIONS)
    doc.status = target
    doc.submitted_at = frappe.utils.now_datetime()
    doc.save(ignore_permissions=True)
    append_event(action="office_application.submit", record_type=doc.doctype, record_name=doc.name, reason="Synthetic application submitted")
    return _serialize_office_application(doc)


def _approve_application_office(doc: Any) -> str:
    office_code = f"AQ-OFFICE-{doc.name[-8:].upper()}"
    if frappe.db.exists("Aqari Office", {"office_code": office_code}):
        office = frappe.db.get_value("Aqari Office", {"office_code": office_code}, "name")
    else:
        office_doc = frappe.get_doc(
            {
                "doctype": "Aqari Office",
                "office_code": office_code,
                "office_name": doc.office_name,
                "legal_name": doc.legal_name or doc.office_name,
                "status": "Active",
                "registration_number": doc.registration_reference or f"SYN-{doc.name[-6:].upper()}",
                "governorate": doc.governorate,
                "district": doc.district,
                "address": doc.address,
                "contact_phone": doc.contact_phone,
                "contact_email": doc.contact_email,
                "office_admin_user": doc.applicant_user,
                "synthetic": 1,
            }
        )
        office_doc.insert(ignore_permissions=True)
        office = office_doc.name
    if not frappe.db.exists("Aqari Office Membership", {"office": office, "user": doc.applicant_user}):
        frappe.get_doc(
            {
                "doctype": "Aqari Office Membership",
                "office": office,
                "user": doc.applicant_user,
                "role": "Aqari Office Administrator",
                "status": "Active",
                "joined_on": frappe.utils.today(),
                "purpose": "Synthetic approved office application",
                "synthetic": 1,
            }
        ).insert(ignore_permissions=True)
    user_doc = frappe.get_doc("User", doc.applicant_user)
    if "Aqari Office Administrator" not in {row.role for row in user_doc.roles}:
        user_doc.add_roles("Aqari Office Administrator")
    return office


@frappe.whitelist(methods=["POST"])
def review_office_application(name: str, decision: str, reason: str = "") -> dict[str, Any]:
    user = _require_user()
    if not (is_platform_operator(user) or user_roles(user) & {"Aqari Registration Reviewer", "Aqari Federation Reviewer"}):
        frappe.throw("A registration reviewer role is required", frappe.PermissionError)
    doc = frappe.get_doc("Aqari Office Application", name)
    if doc.status == "Submitted":
        doc.status = "Under Review"
        doc.save(ignore_permissions=True)
    if doc.status != "Under Review":
        frappe.throw("Only submitted applications can be reviewed", frappe.ValidationError)
    target = {"approve": "Approved", "Approve": "Approved", "return": "Correction Required", "Return": "Correction Required", "reject": "Rejected", "Reject": "Rejected"}.get(decision)
    if not target:
        frappe.throw("Decision must be approve, return, or reject", frappe.ValidationError)
    if not reason.strip():
        frappe.throw("A review decision needs a reason", frappe.ValidationError)
    reviewer_role = sorted(user_roles(user) & {"Aqari Registration Reviewer", "Aqari Federation Reviewer"})
    doc.reviewer_user = user
    doc.reviewer_role = reviewer_role[0] if reviewer_role else "Aqari Platform Operator"
    doc.decision_reason = reason
    doc.reviewed_at = frappe.utils.now_datetime()
    doc.status = target
    if target == "Approved":
        doc.approved_office = _approve_application_office(doc)
    doc.save(ignore_permissions=True)
    append_event(action="office_application.review", record_type=doc.doctype, record_name=doc.name, office=doc.approved_office, reason=reason, metadata={"decision": target})
    return _serialize_office_application(doc)


@frappe.whitelist(methods=["POST"])
def approve_or_return_office_application(name: str, approve: bool = True, reason: str = "") -> dict[str, Any]:
    return review_office_application(name, "approve" if _is_true(approve) else "return", reason)


@frappe.whitelist(methods=["POST"])
def withdrawal(name: str | None = None, payload: Any = None, action: str = "create", simulate_presence: bool = False) -> dict[str, Any]:
    """Create or advance one controlled synthetic withdrawal.

    ``action`` is one of ``create``, ``submit``, ``approve``, or ``complete``.
    The explicit action list is deliberately finite and does not dispatch
    arbitrary methods.
    """
    user = _require_user()
    data = _payload(payload)
    if action == "create":
        values = _safe_fields(data, WITHDRAWAL_FIELDS)
        office = _office_for_payload(values, user)
        transaction_name = values.get("transaction")
        if transaction_name:
            transaction_doc = _transaction(transaction_name)
            if transaction_doc.office != office:
                frappe.throw("The withdrawal transaction is outside the selected office", frappe.PermissionError)
        values["office"] = office
        values["status"] = "Draft"
        values["synthetic"] = 1
        doc = frappe.get_doc({"doctype": "Aqari Withdrawal", **values})
        doc.insert(ignore_permissions=True)
        append_event(action="withdrawal.create", record_type=doc.doctype, record_name=doc.name, office=office)
        return _serialize_withdrawal(doc)
    if not name:
        frappe.throw("A withdrawal name is required for this action", frappe.ValidationError)
    doc = frappe.get_doc("Aqari Withdrawal", name)
    if not doc.synthetic:
        frappe.throw("Only synthetic withdrawals are available in this preview", frappe.PermissionError)
    require_office_access(doc.office, user)
    if action == "submit":
        if not has_permission(doc, "write", user):
            frappe.throw("This withdrawal is not editable by the current user", frappe.PermissionError)
        if not _is_true(simulate_presence):
            frappe.throw("The preview requires explicit synthetic presence confirmation", frappe.ValidationError)
        doc.seller_presence_confirmed = 1
        doc.old_buyer_presence_confirmed = 1
        doc.replacement_presence_confirmed = 1
        doc.fingerprint_simulated = 1
        move_withdrawal(doc, "Submitted")
    elif action == "approve":
        if not can_review(user):
            frappe.throw("A reviewer role is required", frappe.PermissionError)
        move_withdrawal(doc, "Approved")
    elif action == "complete":
        if not (can_review(user) or is_platform_operator(user)):
            frappe.throw("A reviewer or platform operator role is required", frappe.PermissionError)
        move_withdrawal(doc, "Completed")
    else:
        frappe.throw("Unsupported withdrawal action", frappe.ValidationError)
    doc.version = int(doc.version or 1) + 1
    if doc.status == "Submitted":
        doc.submitted_at = frappe.utils.now_datetime()
    if doc.status == "Completed":
        doc.completed_at = frappe.utils.now_datetime()
    doc.save(ignore_permissions=True)
    append_event(action=f"withdrawal.{action}", record_type=doc.doctype, record_name=doc.name, office=doc.office, reason=doc.reason)
    return _serialize_withdrawal(doc)
