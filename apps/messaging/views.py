from __future__ import annotations

from django.contrib import messages as django_messages
from django.db.models import Count, F, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import ListView

from apps.activity.helpers import log_change
from apps.core.access import assert_tenant_access, enforce_tenant_manage
from apps.core.mixins import TenantPermissionRequiredMixin

from .forms import NewDirectMessageForm, ReplyForm
from .models import Participant, Thread, send_direct_message


class InboxView(TenantPermissionRequiredMixin, ListView):
    template_name = "messaging/inbox.html"
    context_object_name = "threads"
    paginate_by = 50
    required_permission = "messaging.view_messaging"

    def get_queryset(self):
        return (
            Thread.objects.filter(participants__user=self.request.user)
            .distinct()
            .order_by("-last_message_at")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["unread_count"] = unread_count(self.request)
        return ctx


def unread_count(request) -> int:
    """Total unread messages across this user's threads, computed in a single
    aggregate query and cached on the request for the remainder of its lifecycle.

    Used by `InboxView` AND by the `unread_messages` statistics widget; without
    the cache the same query runs twice per dashboard render.
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return 0
    if not getattr(request, "tenant", None):
        return 0
    cached = getattr(request, "_qerp_unread_count", None)
    if cached is not None:
        return cached
    user = request.user
    tenant = request.tenant
    # `unscoped` plus an explicit tenant filter — works regardless of whether
    # a thread-local tenant scope is currently set (e.g. tests/management
    # commands).
    parts = Participant.unscoped.filter(tenant=tenant, user=user).annotate(
        unread=Count(
            "thread__messages",
            filter=(
                ~Q(thread__messages__sender=user)
                & (
                    Q(last_read_at__isnull=True)
                    | Q(thread__messages__created_at__gt=F("last_read_at"))
                )
            ),
        )
    )
    total = sum(p.unread or 0 for p in parts)
    request._qerp_unread_count = total
    return total


# Kept as a private alias so existing imports (statistics widget) continue
# working without an import-site churn.
_unread_count = unread_count


class ThreadListView(InboxView):
    """Same data as inbox, alternate landing."""
    template_name = "messaging/thread_list.html"


def thread_detail(request, tenant_slug, pk):
    assert_tenant_access(request)
    thread = get_object_or_404(
        Thread.objects.filter(participants__user=request.user),
        pk=pk,
    )
    participant = Participant.objects.filter(thread=thread, user=request.user).first()
    if request.method == "POST":
        # NOTIFICATION threads are server-side read-only — template hiding is
        # not sufficient on its own.
        if thread.kind == Thread.Kind.NOTIFICATION:
            return HttpResponseForbidden("Notifications are read-only.")
        form = ReplyForm(request.POST)
        if form.is_valid():
            msg = form.save(commit=False)
            msg.tenant = request.tenant
            msg.thread = thread
            msg.sender = request.user
            msg.save()
            log_change(request, action="messaging.message.create", obj=msg)
            if participant:
                participant.last_read_at = timezone.now()
                participant.save(update_fields=["last_read_at", "updated_at"])
            return redirect("messaging:thread_detail", tenant_slug=tenant_slug, pk=thread.pk)
    else:
        form = ReplyForm()
        if participant:
            participant.last_read_at = timezone.now()
            participant.save(update_fields=["last_read_at", "updated_at"])
    msgs = thread.messages.select_related("sender").order_by("pk")
    return render(
        request,
        "messaging/thread_detail.html",
        {"thread": thread, "messages_list": msgs, "form": form},
    )


def new_direct(request, tenant_slug):
    # Requires both authentication and tenant access; without this the form
    # below would enumerate all active tenant users to anonymous visitors.
    assert_tenant_access(request)
    if request.method == "POST":
        form = NewDirectMessageForm(request.POST, tenant=request.tenant, sender=request.user)
        if form.is_valid():
            recipient = form.cleaned_data["recipient"]
            body = form.cleaned_data["body"]
            subject = form.cleaned_data.get("subject", "")
            msg = send_direct_message(
                tenant=request.tenant,
                sender=request.user,
                recipient=recipient,
                body=body,
                subject=subject,
            )
            log_change(request, action="messaging.message.create", obj=msg)
            django_messages.success(request, "Message sent.")
            return redirect("messaging:thread_detail", tenant_slug=tenant_slug, pk=msg.thread_id)
    else:
        form = NewDirectMessageForm(tenant=request.tenant, sender=request.user)
    return render(request, "messaging/new_direct.html", {"form": form})
