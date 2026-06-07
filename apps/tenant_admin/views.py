from __future__ import annotations

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView, TemplateView

from apps.accounts.models import User
from apps.activity.helpers import log_change
from apps.activity.models import ActivityLog
from apps.core.access import enforce_tenant_manage
from apps.core.mixins import TenantPermissionRequiredMixin
from apps.tenants.models import Tenant, TenantGroup, TenantModule

from .forms import TenantGroupForm, TenantSettingsForm, TenantUserForm


class TenantAdminMixin(TenantPermissionRequiredMixin):
    required_permission = "tenants.manage_tenant"


class TenantAdminHome(TenantAdminMixin, TemplateView):
    template_name = "tenant_admin/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tenant = self.request.tenant
        ctx["tenant"] = tenant
        ctx["seats_used"] = tenant.active_user_count()
        ctx["seats_limit"] = tenant.effective_seat_limit()
        ctx["active_modules"] = TenantModule.objects.filter(
            tenant=tenant, disabled_at__isnull=True
        ).select_related("module")
        return ctx


# --- Users -----------------------------------------------------------------

class UserListView(TenantAdminMixin, ListView):
    template_name = "tenant_admin/user_list.html"
    context_object_name = "users"
    paginate_by = 50

    def get_queryset(self):
        return User.objects.filter(tenant=self.request.tenant).order_by("username")


def user_create_or_edit(request, tenant_slug, user_id=None):
    enforce_tenant_manage(request, "tenants.manage_tenant")
    instance = None
    if user_id is not None:
        instance = get_object_or_404(User, pk=user_id, tenant=request.tenant)
    if request.method == "POST":
        # Hold the Tenant row for the duration of the seat-limit check + write
        # so two concurrent admin POSTs can't both squeak past the limit.
        # `select_for_update` is a no-op on SQLite and correct on Postgres.
        with transaction.atomic():
            Tenant.objects.select_for_update().get(pk=request.tenant.pk)
            form = TenantUserForm(request.POST, instance=instance, tenant=request.tenant)
            if form.is_valid():
                obj = form.save()
                log_change(
                    request,
                    action="tenant_admin.user.create" if instance is None else "tenant_admin.user.update",
                    obj=obj,
                )
                messages.success(request, "User saved.")
                return redirect("tenant_admin:user_list", tenant_slug=tenant_slug)
    else:
        form = TenantUserForm(instance=instance, tenant=request.tenant)
    return render(
        request,
        "tenant_admin/user_form.html",
        {"form": form, "instance": instance},
    )


def user_delete(request, tenant_slug, user_id):
    enforce_tenant_manage(request, "tenants.manage_tenant")
    instance = get_object_or_404(User, pk=user_id, tenant=request.tenant)
    if request.method == "POST":
        log_change(request, action="tenant_admin.user.delete", obj=instance)
        instance.delete()
        messages.success(request, "User deleted.")
        return redirect("tenant_admin:user_list", tenant_slug=tenant_slug)
    return render(request, "tenant_admin/confirm_delete.html", {"object": instance, "kind": "user"})


# --- Groups ----------------------------------------------------------------

class GroupListView(TenantAdminMixin, ListView):
    template_name = "tenant_admin/group_list.html"
    context_object_name = "tenant_groups"
    paginate_by = 50

    def get_queryset(self):
        return TenantGroup.objects.filter(tenant=self.request.tenant).select_related("group")


def group_create_or_edit(request, tenant_slug, group_id=None):
    enforce_tenant_manage(request, "tenants.manage_tenant")
    instance = None
    if group_id is not None:
        instance = get_object_or_404(TenantGroup, pk=group_id, tenant=request.tenant)
    if request.method == "POST":
        form = TenantGroupForm(request.POST, instance=instance, tenant=request.tenant)
        if form.is_valid():
            obj = form.save()
            log_change(
                request,
                action="tenant_admin.group.create" if instance is None else "tenant_admin.group.update",
                obj=obj,
            )
            messages.success(request, "Group saved.")
            return redirect("tenant_admin:group_list", tenant_slug=tenant_slug)
    else:
        form = TenantGroupForm(instance=instance, tenant=request.tenant)
    return render(request, "tenant_admin/group_form.html", {"form": form, "instance": instance})


def group_delete(request, tenant_slug, group_id):
    enforce_tenant_manage(request, "tenants.manage_tenant")
    instance = get_object_or_404(TenantGroup, pk=group_id, tenant=request.tenant)
    if instance.is_system_managed:
        messages.error(request, "Cannot delete a system-managed group.")
        return redirect("tenant_admin:group_list", tenant_slug=tenant_slug)
    if request.method == "POST":
        log_change(request, action="tenant_admin.group.delete", obj=instance)
        group = instance.group
        # Collect affected user ids BEFORE the cascade clears the M2M.
        from apps.core.context_processors import invalidate_menu_for_user

        affected_user_ids = list(
            group.user_set.filter(tenant=request.tenant).values_list("id", flat=True)
        )
        instance.delete()
        group.delete()
        for uid in affected_user_ids:
            invalidate_menu_for_user(request.tenant.id, uid)
        messages.success(request, "Group deleted.")
        return redirect("tenant_admin:group_list", tenant_slug=tenant_slug)
    return render(request, "tenant_admin/confirm_delete.html", {"object": instance, "kind": "group"})


# --- Settings --------------------------------------------------------------

def settings_view(request, tenant_slug):
    enforce_tenant_manage(request, "tenants.manage_tenant")
    tenant = request.tenant
    settings_obj = tenant.settings
    if request.method == "POST":
        form = TenantSettingsForm(request.POST, request.FILES, instance=settings_obj)
        if form.is_valid():
            obj = form.save()
            log_change(request, action="tenant_admin.settings.update", obj=obj)
            messages.success(request, "Settings saved.")
            return redirect("tenant_admin:settings", tenant_slug=tenant_slug)
    else:
        form = TenantSettingsForm(instance=settings_obj)
    return render(request, "tenant_admin/settings.html", {"form": form, "tenant": tenant})


# --- Activity --------------------------------------------------------------

class ActivityView(TenantAdminMixin, ListView):
    template_name = "tenant_admin/activity.html"
    context_object_name = "logs"
    paginate_by = 50

    def get_queryset(self):
        qs = ActivityLog.objects.filter(tenant=self.request.tenant).select_related("actor", "tenant")
        category = self.request.GET.get("category")
        if category:
            qs = qs.filter(category=category)
        action = self.request.GET.get("action")
        if action:
            qs = qs.filter(action__startswith=action)
        actor = self.request.GET.get("actor")
        if actor:
            qs = qs.filter(actor_username_snapshot__icontains=actor)
        return qs.order_by("-timestamp")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["categories"] = ActivityLog.Category.choices
        ctx["filters"] = {
            "category": self.request.GET.get("category", ""),
            "action": self.request.GET.get("action", ""),
            "actor": self.request.GET.get("actor", ""),
        }
        return ctx
