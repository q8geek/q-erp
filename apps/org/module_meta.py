MODULE = {
    "code": "org",
    "name": "Organisation",
    "description": "Departments, teams, memberships, heads-of.",
    "is_core": True,
    "app_label": "org",
    "url_namespace": "org",
    "permissions": [
        ("view_org", "Can view organisation"),
        ("manage_org", "Can manage organisation"),
    ],
    "menu": [
        {"label": "Departments", "url_name": "org:department_list"},
        {"label": "Teams", "url_name": "org:team_list"},
        {"label": "Memberships", "url_name": "org:membership_list"},
    ],
}
