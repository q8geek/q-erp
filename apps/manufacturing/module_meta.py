MODULE = {
    "code": "manufacturing",
    "name": "Manufacturing",
    "description": "Bills of materials and work orders.",
    "is_core": False,
    "app_label": "manufacturing",
    "url_namespace": "manufacturing",
    "permissions": [
        ("view_manufacturing", "Can view manufacturing"),
        ("manage_manufacturing", "Can manage manufacturing"),
    ],
    "menu": [
        {"label": "BOMs", "url_name": "manufacturing:billofmaterials_list"},
        {"label": "Work Orders", "url_name": "manufacturing:workorder_list"},
    ],
}
