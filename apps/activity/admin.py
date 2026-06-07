from django.contrib import admin

from .models import ActivityLog


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "tenant", "actor_username_snapshot", "category", "action", "status_code")
    list_filter = ("category", "tenant")
    search_fields = ("action", "actor_username_snapshot", "object_repr")
    date_hierarchy = "timestamp"
    readonly_fields = tuple(f.name for f in ActivityLog._meta.fields)
