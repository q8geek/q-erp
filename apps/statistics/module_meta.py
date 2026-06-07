MODULE = {
    "code": "statistics",
    "name": "Statistics",
    "description": "Per-tenant dashboard widgets and performance metrics.",
    "is_core": True,
    "app_label": "statistics",
    "url_namespace": "statistics",
    "permissions": [
        ("view_statistics", "Can view statistics"),
        ("manage_statistics", "Can configure statistics"),
    ],
    "menu": [
        {"label": "Dashboard", "url_name": "statistics:dashboard"},
        {"label": "Configure", "url_name": "statistics:configure"},
    ],
}
