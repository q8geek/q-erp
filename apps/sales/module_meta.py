MODULE = {
    "code": "sales",
    "name": "Sales / Order Management",
    "description": "Quotes and sales orders.",
    "is_core": False,
    "app_label": "sales",
    "url_namespace": "sales",
    "permissions": [
        ("view_sales", "Can view sales"),
        ("manage_sales", "Can manage sales"),
    ],
    "menu": [
        {"label": "Quotes", "url_name": "sales:quote_list"},
        {"label": "Sales Orders", "url_name": "sales:salesorder_list"},
    ],
}
