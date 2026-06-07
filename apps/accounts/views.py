"""Routing helpers used by auth flows."""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse


@login_required
def post_login_redirect(request):
    """Send the user to the correct landing page after login."""
    user = request.user
    if user.is_system_admin:
        return HttpResponseRedirect(reverse("sys_admin:dashboard"))
    if user.tenant_id:
        return HttpResponseRedirect(
            reverse("dashboard:home", kwargs={"tenant_slug": user.tenant.slug})
        )
    # Bootstrap superuser without a tenant: go to django admin
    return redirect("/admin/")
