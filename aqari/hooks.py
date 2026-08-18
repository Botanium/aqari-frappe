from __future__ import annotations

app_name = "aqari"
app_title = "Aqari"
app_publisher = "Aqari platform team"
app_description = "Synthetic real-estate office and transaction workflows"
app_email = "engineering@example.invalid"
app_license = "MIT"
app_version = "0.1.0"

required_apps = ["frappe"]
after_install = "aqari.setup.install.after_install"

permission_query_conditions = {
    "Aqari Office Application": "aqari.permissions.office_application_query",
    "Aqari Office": "aqari.permissions.office_record_query",
    "Aqari Office Membership": "aqari.permissions.office_membership_query",
    "Aqari Party": "aqari.permissions.office_scoped_query",
    "Aqari Property": "aqari.permissions.office_scoped_query",
    "Aqari Transaction": "aqari.permissions.office_scoped_query",
    "Aqari Transaction Review": "aqari.permissions.office_scoped_query",
    "Aqari Withdrawal": "aqari.permissions.office_scoped_query",
    "Aqari Audit Event": "aqari.permissions.office_scoped_query",
}

has_permission = {
    "Aqari Office Application": "aqari.permissions.has_permission",
    "Aqari Office": "aqari.permissions.has_permission",
    "Aqari Office Membership": "aqari.permissions.has_permission",
    "Aqari Party": "aqari.permissions.has_permission",
    "Aqari Property": "aqari.permissions.has_permission",
    "Aqari Transaction": "aqari.permissions.has_permission",
    "Aqari Transaction Review": "aqari.permissions.has_permission",
    "Aqari Withdrawal": "aqari.permissions.has_permission",
    "Aqari Audit Event": "aqari.permissions.has_permission",
}

# Keep the API surface explicit.  Do not add a generic resource or method
# proxy: every portal action has a named function in aqari.api.
whitelisted_methods = [
    "aqari.api.health",
    "aqari.api.session",
    "aqari.api.dashboard",
    "aqari.api.list_transactions",
    "aqari.api.transaction_detail",
    "aqari.api.create_transaction",
    "aqari.api.update_transaction",
    "aqari.api.submit_transaction",
    "aqari.api.review_transaction",
    "aqari.api.withdrawal",
    "aqari.api.create_office_application",
    "aqari.api.update_office_application",
    "aqari.api.submit_office_application",
    "aqari.api.review_office_application",
    "aqari.api.approve_or_return_office_application",
]
