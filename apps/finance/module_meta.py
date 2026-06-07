MODULE = {
    "code": "finance",
    "name": "Finance & Accounting",
    "description": "General ledger accounts and core accounting structures.",
    "is_core": True,
    "app_label": "finance",
    "url_namespace": "finance",
    "permissions": [
        ("view_finance", "Can view finance"),
        ("manage_finance", "Can manage finance"),
    ],
    "menu": [
        {"label": "Accounts", "url_name": "finance:account_list"},
    ],
}
