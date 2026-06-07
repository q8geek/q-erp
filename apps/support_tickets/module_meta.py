MODULE = {
    "code": "support_tickets",
    "name": "Support Tickets",
    "description": "Ticket categories, tickets, replies.",
    "is_core": False,
    "app_label": "support_tickets",
    "url_namespace": "support_tickets",
    "permissions": [
        ("view_support_tickets", "Can view support tickets"),
        ("manage_support_tickets", "Can manage support tickets"),
    ],
    "menu": [
        {"label": "Tickets", "url_name": "support_tickets:ticket_list"},
        {"label": "Categories", "url_name": "support_tickets:ticketcategory_list"},
    ],
}
