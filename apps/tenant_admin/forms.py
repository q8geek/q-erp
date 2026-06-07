from __future__ import annotations

from django import forms
from django.contrib.auth.models import Group, Permission

from apps.accounts.models import User
from apps.tenants.models import TenantGroup, TenantSettings


class TenantSettingsForm(forms.ModelForm):
    class Meta:
        model = TenantSettings
        exclude = ("tenant",)


class TenantUserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, required=False,
                               help_text="Leave blank to keep current password (on edit).")
    groups = forms.ModelMultipleChoiceField(queryset=Group.objects.none(), required=False)

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "phone", "is_active", "is_disabled", "groups")

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        if tenant:
            self.fields["groups"].queryset = Group.objects.filter(tenant_group__tenant=tenant)
            if self.instance.pk:
                self.fields["groups"].initial = self.instance.groups.all()

    def clean(self):
        cleaned = super().clean()
        if not self.tenant:
            return cleaned
        would_be_active = cleaned.get("is_active", True) and not cleaned.get("is_disabled", False)
        currently_active = bool(
            self.instance.pk and self.instance.is_active and not self.instance.is_disabled
        )
        if would_be_active and not currently_active and not self.tenant.has_seat_available():
            raise forms.ValidationError(
                f"Seat limit reached ({self.tenant.effective_seat_limit()}). Disable another user first."
            )
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.tenant = self.tenant
        user.is_system_admin = False
        pwd = self.cleaned_data.get("password")
        if pwd:
            user.set_password(pwd)
        elif not user.pk:
            # Default unusable password on create when none supplied
            user.set_unusable_password()
        if commit:
            user.save()
            self.save_m2m()
            user.groups.set(self.cleaned_data.get("groups") or [])
            # Group membership drives menu visibility -> invalidate this user's
            # menu cache so role changes show up on the next request.
            if user.tenant_id:
                from apps.core.context_processors import invalidate_menu_for_user

                invalidate_menu_for_user(user.tenant_id, user.id)
        return user


class TenantGroupForm(forms.ModelForm):
    name = forms.CharField(max_length=120)
    permissions = forms.ModelMultipleChoiceField(queryset=Permission.objects.none(), required=False)

    class Meta:
        model = TenantGroup
        fields = ("description",)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        # Permission queryset limited to active modules' permissions + tenants.manage_tenant
        active_codes = list(tenant.active_module_codes()) if tenant else []
        perm_qs = Permission.objects.filter(
            content_type__app_label__in=active_codes + ["tenants"]
        )
        self.fields["permissions"].queryset = perm_qs
        if self.instance.pk:
            self.fields["name"].initial = self.instance.group.name.split(":", 1)[-1]
            self.fields["permissions"].initial = self.instance.group.permissions.all()

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Name required.")
        return name

    def save(self, commit=True):
        tgroup = super().save(commit=False)
        tgroup.tenant = self.tenant
        prefix = f"t{self.tenant.id}:"
        new_name = prefix + self.cleaned_data["name"]
        if tgroup.pk:
            tgroup.group.name = new_name
            tgroup.group.save()
        else:
            group, _ = Group.objects.get_or_create(name=new_name)
            tgroup.group = group
        if commit:
            tgroup.save()
            tgroup.group.permissions.set(self.cleaned_data.get("permissions") or [])
            # Permission changes on a group conceptually affect every user in
            # that group under this tenant. Rather than walking the member list
            # (O(N) cache deletes), bump the tenant's menu version once: every
            # per-(tenant, user) cache entry under the old version becomes
            # unreachable on the next read. Single O(1) cache op vs O(N).
            if self.tenant is not None:
                from apps.core.context_processors import invalidate_menu_for_tenant

                invalidate_menu_for_tenant(self.tenant.id)
        return tgroup
