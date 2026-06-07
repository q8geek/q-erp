MODULE = {
    "code": "inventory",
    "name": "Inventory",
    "description": "Items, warehouses, stock structure.",
    "is_core": True,
    "app_label": "inventory",
    "url_namespace": "inventory",
    "permissions": [
        ("view_inventory", "Can view inventory"),
        ("manage_inventory", "Can manage inventory"),
    ],
    "menu": [
        {"label": "Warehouses", "url_name": "inventory:warehouse_list"},
        {"label": "Items", "url_name": "inventory:item_list"},
    ],
}
