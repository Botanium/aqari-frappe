"""Append-only audit event helpers.

Audit payloads contain metadata only.  Protected KYC, deed, biometric, and
payment contents are never copied into the audit record.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import frappe

from .permissions import current_user, user_roles


AUDIT_DOCTYPE = "Aqari Audit Event"
SENSITIVE_KEYS = {"national_number", "identity_front", "identity_back", "portrait", "biometric", "signature"}


def _safe_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _safe_metadata(item) for key, item in value.items() if str(key) not in SENSITIVE_KEYS}
    if isinstance(value, (list, tuple)):
        return [_safe_metadata(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _canonical(value: Any) -> str:
    return json.dumps(_safe_metadata(value), sort_keys=True, separators=(",", ":"), default=str)


def append_event(
    *,
    action: str,
    record_type: str,
    record_name: str,
    office: str | None = None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
    actor_user: str | None = None,
    actor_role: str | None = None,
) -> str:
    actor_user = actor_user or current_user()
    actor_role = actor_role or _primary_role(actor_user)
    safe_metadata = _safe_metadata(metadata or {})
    event_timestamp = frappe.utils.now_datetime().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    previous = frappe.get_all(
        AUDIT_DOCTYPE,
        filters={"office": office} if office else {},
        fields=["event_hash"],
        order_by="creation desc",
        limit_page_length=1,
    )
    previous_hash = previous[0].event_hash if previous and previous[0].event_hash else ""
    digest_input = {
        "action": action,
        "record_type": record_type,
        "record_name": record_name,
        "office": office or "",
        "actor_user": actor_user,
        "actor_role": actor_role,
        "reason": reason or "",
        "metadata": safe_metadata,
        "event_timestamp": event_timestamp,
        "previous_event_hash": previous_hash,
    }
    event_hash = hashlib.sha256(_canonical(digest_input).encode("utf-8")).hexdigest()
    doc = frappe.get_doc(
        {
            "doctype": AUDIT_DOCTYPE,
            "office": office,
            "actor_user": actor_user,
            "actor_role": actor_role,
            "action": action,
            "record_type": record_type,
            "record_name": record_name,
            "reason": reason,
            "event_timestamp": event_timestamp,
            "metadata_json": json.dumps(safe_metadata, sort_keys=True, separators=(",", ":")),
            "previous_event_hash": previous_hash,
            "event_hash": event_hash,
            "synthetic": 1,
        }
    )
    doc.flags.ignore_permissions = True
    doc.flags._aqari_audit_insert = True
    doc.insert(ignore_permissions=True)
    return doc.name


def _primary_role(user: str) -> str:
    roles = sorted(user_roles(user))
    return roles[0] if roles else "Unknown"
