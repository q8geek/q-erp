from __future__ import annotations

import json

from django import forms

from .models import Rule
from .registry import action_choices, event_choices


class RuleForm(forms.ModelForm):
    condition_json = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 5}),
        required=False,
        help_text='JSON object. Empty = always match. Example: {"qty_on_hand": {"<": 10}}',
    )
    action_params_json = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 5}),
        required=False,
        help_text='JSON object of action parameters. See docs for each action type.',
    )

    class Meta:
        model = Rule
        fields = ("name", "event_type", "action_type", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["event_type"] = forms.ChoiceField(choices=[("", "---")] + event_choices())
        self.fields["action_type"] = forms.ChoiceField(choices=[("", "---")] + action_choices())
        if self.instance and self.instance.pk:
            self.fields["condition_json"].initial = json.dumps(self.instance.condition or {}, indent=2)
            self.fields["action_params_json"].initial = json.dumps(self.instance.action_params or {}, indent=2)

    def clean_condition_json(self):
        raw = (self.cleaned_data.get("condition_json") or "").strip()
        if not raw:
            return {}
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f"Invalid JSON: {exc}") from exc
        if not isinstance(obj, dict):
            raise forms.ValidationError("Condition must be a JSON object.")
        return obj

    def clean_action_params_json(self):
        raw = (self.cleaned_data.get("action_params_json") or "").strip()
        if not raw:
            return {}
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f"Invalid JSON: {exc}") from exc
        if not isinstance(obj, dict):
            raise forms.ValidationError("Action params must be a JSON object.")
        return obj

    def save(self, commit=True):
        rule = super().save(commit=False)
        rule.condition = self.cleaned_data["condition_json"]
        rule.action_params = self.cleaned_data["action_params_json"]
        if commit:
            rule.save()
        return rule
