MODULE = {
    "code": "procurement",
    "name": "Procurement",
    "description": "Suppliers and purchase orders.",
    "is_core": True,
    "app_label": "procurement",
    "url_namespace": "procurement",
    "permissions": [
        ("view_procurement", "Can view procurement"),
        ("manage_procurement", "Can manage procurement"),
    ],
    "menu": [
        {"label": "Suppliers", "url_name": "procurement:supplier_list"},
        {"label": "Purchase Orders", "url_name": "procurement:purchaseorder_list"},
    ],
}
