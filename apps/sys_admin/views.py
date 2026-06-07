from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import ListView, TemplateView

from apps.accounts.models import SystemAdminTenant, User
from apps.activity.helpers import log_change
from apps.activity.models import ActivityLog
from apps.core.mixins import SystemAdminRequiredMixin
from apps.tenants.models import Module, Plan, Subscription, Tenant, TenantGroup, TenantModule

from .forms import SubscriptionForm, SystemAdminUserForm, TenantBootstrapForm, TenantForm


class SysAdminDashboard(SystemAdminRequiredMixin, TemplateView):
    template_name = "sys_admin/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Materialise once: the template iterates `tenants` and we need the
        # count separately. Two `accessible_tenants()` invocations would
        # otherwise run two identical queries.
        tenants = list(self.request.user.accessible_tenants())
        ctx["tenants"] = tenants
        ctx["tenant_count"] = len(tenants)
        ctx["module_count"] = Module.objects.count()
        ctx["plan_count"] = Plan.objects.count()
        return ctx


class TenantListView(SystemAdminRequiredMixin, ListView):
    template_name = "sys_admin/tenant_list.html"
    context_object_name = "tenants"
    paginate_by = 50

    def get_queryset(self):
        return self.request.user.accessible_tenants().order_by("name")


def _check_tenant_access(user, tenant):
    if user.is_global_admin:
        return
    if not SystemAdminTenant.objects.filter(user=user, tenant=tenant).exists():
        raise PermissionDenied("Not authorized for this tenant.")


def tenant_create(request):
    if not (request.user.is_authenticated and request.user.is_system_admin):
        raise PermissionDenied()
    if not request.user.is_global_admin:
        raise PermissionDenied("Only global admins can create tenants.")
    if request.method == "POST":
        form = TenantBootstrapForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                tenant = Tenant.objects.create(
                    slug=form.cleaned_data["slug"], name=form.cleaned_data["name"]
                )
                plan = form.cleaned_data.get("plan")
                if plan:
                    Subscription.objects.create(tenant=tenant, plan=plan)
                    # Activate add-on modules from the plan. Assign a
                    # fresh sort_order per new row so the sidebar order
                    # is stable instead of all ties at 0.
                    for module in plan.modules.all():
                        TenantModule.objects.get_or_create(
                            tenant=tenant,
                            module=module,
                            defaults={
                                "sort_order": TenantModule.next_sort_order_for(tenant),
                            },
                        )
                # Create initial admin user
                admin_user = User.objects.create_user(
                    username=form.cleaned_data["admin_username"],
                    email=form.cleaned_data["admin_email"],
                    password=form.cleaned_data["admin_password"],
                    tenant=tenant,
                )
                # Add to Tenant Administrators group
                tgroup = TenantGroup.objects.filter(
                    tenant=tenant, is_system_managed=True
                ).first()
                if tgroup:
                    admin_user.groups.add(tgroup.group)
            log_change(request, action="sys_admin.tenant.create", obj=tenant)
            messages.success(request, f"Tenant '{tenant.slug}' created with admin '{admin_user.username}'.")
            return redirect("sys_admin:tenant_detail", tenant_id=tenant.id)
    else:
        form = TenantBootstrapForm()
    return render(request, "sys_admin/tenant_create.html", {"form": form})


def tenant_detail(request, tenant_id):
    if not request.user.is_system_admin:
        raise PermissionDenied()
    tenant = get_object_or_404(Tenant, pk=tenant_id)
    _check_tenant_access(request.user, tenant)
    subscription = tenant.subscriptions.filter(is_active=True).first()
    tenant_modules = TenantModule.objects.filter(tenant=tenant).select_related("module").order_by(
        "module__is_core", "module__name"
    )
    return render(
        request,
        "sys_admin/tenant_detail.html",
        {
            "tenant": tenant,
            "subscription": subscription,
            "tenant_modules": tenant_modules,
            "all_modules": Module.objects.all().order_by("is_core", "name"),
            "plans": Plan.objects.filter(is_active=True),
        },
    )


def tenant_edit(request, tenant_id):
    if not request.user.is_system_admin:
        raise PermissionDenied()
    tenant = get_object_or_404(Tenant.objects, pk=tenant_id)
    _check_tenant_access(request.user, tenant)
    if request.method == "POST":
        form = TenantForm(request.POST, instance=tenant)
        if form.is_valid():
            obj = form.save()
            log_change(request, action="sys_admin.tenant.update", obj=obj)
            messages.success(request, "Tenant updated.")
            return redirect("sys_admin:tenant_detail", tenant_id=tenant.id)
    else:
        form = TenantForm(instance=tenant)
    return render(request, "sys_admin/tenant_edit.html", {"form": form, "tenant": tenant})


def tenant_module_toggle(request, tenant_id, module_id):
    if not request.user.is_system_admin:
        raise PermissionDenied()
    tenant = get_object_or_404(Tenant.objects, pk=tenant_id)
    _check_tenant_access(request.user, tenant)
    module = get_object_or_404(Module, pk=module_id)
    if request.method != "POST":
        return redirect("sys_admin:tenant_detail", tenant_id=tenant.id)
    tm, created = TenantModule.objects.get_or_create(
        tenant=tenant,
        module=module,
        defaults={"sort_order": TenantModule.next_sort_order_for(tenant)},
    )
    if created:
        action = "enable"
    else:
        if tm.disabled_at is None:
            tm.disabled_at = timezone.now()
            action = "disable"
        else:
            tm.disabled_at = None
            tm.enabled_at = timezone.now()
            action = "enable"
        tm.save()
    log_change(
        request,
        action=f"sys_admin.tenant.module.{action}",
        obj=tm,
        extra={"module_code": module.code, "is_core": module.is_core},
    )
    # Bust the per-(tenant, user) menu cache so the change is reflected on
    # the very next request, and defensively drop any per-instance active
    # module code cache attached to the tenant object.
    from apps.core.context_processors import invalidate_menu_for_tenant

    invalidate_menu_for_tenant(tenant.id)
    if hasattr(tenant, "_active_module_codes_cache"):
        del tenant._active_module_codes_cache
    if module.is_core and action == "disable":
        messages.warning(request, f"Core module '{module.code}' disabled for tenant — this is a non-standard action.")
    else:
        messages.success(request, f"Module '{module.code}' {action}d.")
    return redirect("sys_admin:tenant_detail", tenant_id=tenant.id)


def subscription_edit(request, tenant_id):
    if not request.user.is_system_admin:
        raise PermissionDenied()
    tenant = get_object_or_404(Tenant.objects, pk=tenant_id)
    _check_tenant_access(request.user, tenant)
    subscription = tenant.subscriptions.filter(is_active=True).first()
    if request.method == "POST":
        form = SubscriptionForm(request.POST, instance=subscription)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = tenant
            obj.save()
            # Sync add-on TenantModule rows with the plan's modules
            # (don't remove existing). New rows get a fresh sort_order
            # so they land at the bottom of the sidebar instead of
            # tying at 0 and falling back to alphabetical.
            if obj.plan:
                for m in obj.plan.modules.all():
                    TenantModule.objects.get_or_create(
                        tenant=tenant,
                        module=m,
                        defaults={
                            "sort_order": TenantModule.next_sort_order_for(tenant),
                        },
                    )
            log_change(request, action="sys_admin.subscription.update", obj=obj)
            messages.success(request, "Subscription updated.")
            return redirect("sys_admin:tenant_detail", tenant_id=tenant.id)
    else:
        form = SubscriptionForm(instance=subscription)
    return render(request, "sys_admin/subscription_edit.html", {"form": form, "tenant": tenant})


# --- System admin user management (global admins only) -------------------

def sysadmin_user_list(request):
    if not (request.user.is_system_admin and request.user.is_global_admin):
        raise PermissionDenied()
    qs = User.objects.filter(is_system_admin=True).order_by("username")
    return render(request, "sys_admin/sysadmin_list.html", {"users": qs})


def sysadmin_user_create(request):
    if not (request.user.is_system_admin and request.user.is_global_admin):
        raise PermissionDenied()
    if request.method == "POST":
        form = SystemAdminUserForm(request.POST)
        if form.is_valid():
            obj = form.save()
            log_change(request, action="sys_admin.sysadmin.create", obj=obj)
            messages.success(request, "System admin created.")
            return redirect("sys_admin:sysadmin_list")
    else:
        form = SystemAdminUserForm()
    return render(request, "sys_admin/sysadmin_form.html", {"form": form, "instance": None})


# --- Activity (system-level + scoped tenants) ----------------------------

class SysActivityView(SystemAdminRequiredMixin, ListView):
    template_name = "sys_admin/activity.html"
    context_object_name = "logs"
    paginate_by = 50

    def get_queryset(self):
        user = self.request.user
        qs = ActivityLog.objects.all().select_related("actor", "tenant")
        if not user.is_global_admin:
            from django.db.models import Q
            tenant_ids = list(user.accessible_tenants().values_list("id", flat=True))
            # NOTE: Do not include `Q(tenant__isnull=True, actor__isnull=True,
            # category=AUTH)` here — that clause matched every failed-login
            # row in the system (no tenant, no actor) and leaked foreign
            # tenants' login attempts (usernames + IPs) to non-global admins.
            qs = qs.filter(
                Q(tenant_id__in=tenant_ids)
                | Q(tenant__isnull=True, actor=user)
            )
        category = self.request.GET.get("category")
        if category:
            qs = qs.filter(category=category)
        action = self.request.GET.get("action")
        if action:
            qs = qs.filter(action__startswith=action)
        return qs.order_by("-timestamp")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["categories"] = ActivityLog.Category.choices
        ctx["filters"] = {
            "category": self.request.GET.get("category", ""),
            "action": self.request.GET.get("action", ""),
        }
        return ctx
