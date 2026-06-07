from __future__ import annotations

from django import forms

from apps.accounts.models import User
from apps.tenants.models import Plan, Subscription, Tenant


class TenantForm(forms.ModelForm):
    class Meta:
        model = Tenant
        fields = ("slug", "name", "is_active")


class TenantBootstrapForm(forms.Form):
    """Form to create a tenant + initial admin + subscription in one step."""
    slug = forms.SlugField()
    name = forms.CharField(max_length=200)
    plan = forms.ModelChoiceField(queryset=Plan.objects.filter(is_active=True), required=False)
    admin_username = forms.CharField(max_length=150)
    admin_email = forms.EmailField()
    admin_password = forms.CharField(widget=forms.PasswordInput)


class SubscriptionForm(forms.ModelForm):
    class Meta:
        model = Subscription
        fields = ("plan", "seat_limit_override", "starts_at", "ends_at", "is_active")


class SystemAdminUserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, required=False)

    class Meta:
        model = User
        fields = ("username", "email", "is_active", "is_global_admin")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_system_admin = True
        user.tenant = None
        pwd = self.cleaned_data.get("password")
        if pwd:
            user.set_password(pwd)
        elif not user.pk:
            user.set_unusable_password()
        if commit:
            user.save()
        return user
