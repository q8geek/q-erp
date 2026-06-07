from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView

from apps.activity.helpers import log_change
from apps.core.access import enforce_tenant_manage
from apps.core.mixins import TenantPermissionRequiredMixin

from .forms import RuleForm
from .models import Rule, RuleRun
from .registry import all_actions, all_events


class RuleListView(TenantPermissionRequiredMixin, ListView):
    template_name = "automation/rule_list.html"
    context_object_name = "rules"
    required_permission = "automation.view_automation"
    paginate_by = 50

    def get_queryset(self):
        return Rule.objects.all().order_by("name")


def rule_create_or_edit(request, tenant_slug, pk=None):
    enforce_tenant_manage(request, "automation.manage_automation")
    instance = None
    if pk is not None:
        instance = get_object_or_404(Rule.objects.all(), pk=pk)
    if request.method == "POST":
        form = RuleForm(request.POST, instance=instance)
        if form.is_valid():
            rule = form.save(commit=False)
            rule.tenant = request.tenant
            rule.save()
            log_change(
                request,
                action="automation.rule.create" if instance is None else "automation.rule.update",
                obj=rule,
            )
            messages.success(request, "Rule saved.")
            return redirect("automation:rule_list", tenant_slug=tenant_slug)
    else:
        form = RuleForm(instance=instance)
    return render(
        request,
        "automation/rule_form.html",
        {
            "form": form,
            "instance": instance,
            "events": all_events(),
            "actions": all_actions(),
        },
    )


def rule_delete(request, tenant_slug, pk):
    enforce_tenant_manage(request, "automation.manage_automation")
    instance = get_object_or_404(Rule.objects.all(), pk=pk)
    if request.method == "POST":
        log_change(request, action="automation.rule.delete", obj=instance)
        instance.delete()
        messages.success(request, "Rule deleted.")
        return redirect("automation:rule_list", tenant_slug=tenant_slug)
    return render(
        request,
        "automation/confirm_delete.html",
        {"object": instance},
    )


class RuleRunListView(TenantPermissionRequiredMixin, ListView):
    template_name = "automation/rulerun_list.html"
    context_object_name = "runs"
    required_permission = "automation.view_automation"
    paginate_by = 100

    def get_queryset(self):
        qs = RuleRun.objects.select_related("rule", "triggered_by").order_by("-pk")
        rule_id = self.request.GET.get("rule")
        if rule_id:
            qs = qs.filter(rule_id=rule_id)
        return qs
