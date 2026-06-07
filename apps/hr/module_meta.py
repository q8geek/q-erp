MODULE = {
    "code": "hr",
    "name": "Human Resources",
    "description": "Employees and leave (org structure lives in apps/org).",
    "is_core": False,
    "app_label": "hr",
    "url_namespace": "hr",
    "permissions": [
        ("view_hr", "Can view HR"),
        ("manage_hr", "Can manage HR"),
    ],
    "menu": [
        {"label": "Employees", "url_name": "hr:employee_list"},
        {"label": "Leave Requests", "url_name": "hr:leaverequest_list"},
    ],
}
