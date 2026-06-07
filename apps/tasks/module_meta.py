MODULE = {
    "code": "tasks",
    "name": "Tasks",
    "description": "Personal and project-linked tasks.",
    "is_core": True,
    "app_label": "tasks",
    "url_namespace": "tasks",
    "permissions": [
        ("view_tasks", "Can view tasks"),
        ("manage_tasks", "Can manage tasks"),
    ],
    "menu": [
        {"label": "All Tasks", "url_name": "tasks:task_list"},
        {"label": "My Tasks", "url_name": "tasks:my_tasks"},
    ],
}
