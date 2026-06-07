MODULE = {
    "code": "automation",
    "name": "Automation",
    "description": "Trigger/event/action rules configurable per tenant.",
    "is_core": True,
    "app_label": "automation",
    "url_namespace": "automation",
    "permissions": [
        ("view_automation", "Can view automation rules"),
        ("manage_automation", "Can manage automation rules"),
    ],
    "menu": [
        {"label": "Rules", "url_name": "automation:rule_list"},
        {"label": "Run History", "url_name": "automation:rulerun_list"},
    ],
}
