MODULE = {
    "code": "assets",
    "name": "Fixed Assets",
    "description": "Asset categories and individual assets.",
    "is_core": False,
    "app_label": "assets",
    "url_namespace": "assets",
    "permissions": [
        ("view_assets", "Can view assets"),
        ("manage_assets", "Can manage assets"),
    ],
    "menu": [
        {"label": "Categories", "url_name": "assets:assetcategory_list"},
        {"label": "Assets", "url_name": "assets:asset_list"},
    ],
}
