MODULE = {
    "code": "crm",
    "name": "Customer Relationship Management",
    "description": "Leads, customers, opportunities.",
    "is_core": False,
    "app_label": "crm",
    "url_namespace": "crm",
    "permissions": [
        ("view_crm", "Can view CRM"),
        ("manage_crm", "Can manage CRM"),
    ],
    "menu": [
        {"label": "Leads", "url_name": "crm:lead_list"},
        {"label": "Customers", "url_name": "crm:customer_list"},
        {"label": "Opportunities", "url_name": "crm:opportunity_list"},
    ],
}
