import math
from decimal import Decimal
from decimal import InvalidOperation

from django import forms

from apps.planning.models import DeveloperProfile
from apps.planning.models import Leave
from apps.planning.models import Project


def _clean_name_chars(value: str, label: str) -> str:
    if "||" in value or "\t" in value:
        msg = f"{label} may not contain '||' or tab characters."
        raise forms.ValidationError(msg)
    return value


class EffortWeeksField(forms.DecimalField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("min_value", Decimal("0"))
        kwargs.setdefault("max_digits", 6)
        kwargs.setdefault("decimal_places", 2)
        super().__init__(*args, **kwargs)

    def clean(self, value):
        value = super().clean(value)
        if value in (None, ""):
            return Decimal("0")
        try:
            as_float = float(value)
        except (TypeError, ValueError) as err:
            msg = "Enter a valid resourced effort value."
            raise forms.ValidationError(msg) from err
        if not math.isfinite(as_float):
            msg = "Enter a valid resourced effort value."
            raise forms.ValidationError(msg)
        return value


class ProjectWriteForm(forms.Form):
    name = forms.CharField(required=True, max_length=255)
    effort_resourced = EffortWeeksField()
    dev_lead = forms.IntegerField(required=False)
    science_lead = forms.IntegerField(required=False)
    science_lead_name = forms.CharField(required=False, max_length=255)
    continuation_of = forms.IntegerField(required=False)
    streams = forms.CharField(required=False)
    tags = forms.CharField(required=False)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            msg = "Project name is required."
            raise forms.ValidationError(msg)
        return _clean_name_chars(name, "Project name")

    def clean_streams(self):
        return [n for n in self.data.getlist("streams") if n]

    def clean_tags(self):
        return [n for n in self.data.getlist("tags") if n]

    def clean(self):
        cleaned = super().clean()
        try:
            cleaned["effort_resourced"] = Decimal(
                cleaned.get("effort_resourced", 0) or 0
            )
        except (InvalidOperation, TypeError):
            self.add_error("effort_resourced", "Enter a valid resourced effort value.")
        return cleaned


class PhaseCreateForm(forms.Form):
    developer = forms.ModelChoiceField(queryset=DeveloperProfile.objects.all())
    project = forms.ModelChoiceField(queryset=Project.objects.all())
    start_date = forms.DateField()
    end_date = forms.DateField()
    effort_multiplier = forms.FloatField(required=False, min_value=0.0, max_value=1.0)
    lane_pk = forms.CharField(required=False)

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "End date must not be before start date.")
        if cleaned.get("effort_multiplier") is None:
            cleaned["effort_multiplier"] = 1.0
        return cleaned


class PhaseEditForm(PhaseCreateForm):
    pass


class LeaveCreateForm(forms.ModelForm):
    class Meta:
        model = Leave
        fields = ["developer", "start_date", "end_date"]


class LeaveUpdateForm(forms.ModelForm):
    class Meta:
        model = Leave
        fields = ["start_date", "end_date"]
