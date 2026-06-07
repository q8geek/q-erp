MODULE = {
    "code": "documents",
    "name": "Documents Library",
    "description": "Files and folders with tenant-scoped storage.",
    "is_core": False,
    "app_label": "documents",
    "url_namespace": "documents",
    "permissions": [
        ("view_documents", "Can view documents"),
        ("manage_documents", "Can manage documents"),
    ],
    "menu": [
        {"label": "Folders", "url_name": "documents:folder_list"},
        {"label": "Documents", "url_name": "documents:document_list"},
        {"label": "Tags", "url_name": "documents:tag_list"},
    ],
}
