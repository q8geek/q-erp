MODULE = {
    "code": "messaging",
    "name": "Messaging & Notifications",
    "description": "Internal user threads and system notification inbox.",
    "is_core": True,
    "app_label": "messaging",
    "url_namespace": "messaging",
    "permissions": [
        ("view_messaging", "Can view messages"),
        ("manage_messaging", "Can manage messages"),
    ],
    "menu": [
        {"label": "Inbox", "url_name": "messaging:inbox"},
        {"label": "All Threads", "url_name": "messaging:thread_list"},
    ],
}
