from __future__ import annotations

from django import forms

from apps.accounts.models import User

from .models import Message


class NewDirectMessageForm(forms.Form):
    recipient = forms.ModelChoiceField(queryset=User.objects.none())
    subject = forms.CharField(max_length=200, required=False)
    body = forms.CharField(widget=forms.Textarea)

    def __init__(self, *args, tenant=None, sender=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant and sender:
            self.fields["recipient"].queryset = User.objects.filter(
                tenant=tenant, is_active=True, is_disabled=False
            ).exclude(pk=sender.pk)


class ReplyForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ("body",)
        widgets = {"body": forms.Textarea(attrs={"rows": 3})}
