MODULE = {
    "code": "projects",
    "name": "Projects & Time Tracking",
    "description": "Projects and timesheets (tasks live in apps/tasks).",
    "is_core": False,
    "app_label": "projects",
    "url_namespace": "projects",
    "permissions": [
        ("view_projects", "Can view projects"),
        ("manage_projects", "Can manage projects"),
    ],
    "menu": [
        {"label": "Projects", "url_name": "projects:project_list"},
        {"label": "Timesheets", "url_name": "projects:timesheet_list"},
    ],
}
