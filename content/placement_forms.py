from django import forms

from .models import Company, ContentStatus, NoticeContest
from .placement_services import MAX_NOTE_LENGTH, PROJECT_PROMPTS


class NoticeForm(forms.ModelForm):
    class Meta:
        model = NoticeContest
        fields = ("kind", "title", "description", "date")
        labels = {"kind": "Type", "date": "Date"}
        help_texts = {"date": "The notice date, or the day of the contest."}
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "description": forms.Textarea(attrs={"rows": 6}),
        }


class AddApplicationForm(forms.Form):
    company = forms.ModelChoiceField(queryset=Company.objects.none(), label="Company", empty_label="Choose a company")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        tracked = user.applications.values_list("company_id", flat=True) if user is not None else []
        self.fields["company"].queryset = (
            Company.objects.filter(status=ContentStatus.PUBLISHED).exclude(pk__in=list(tracked)).order_by("name")
        )


class ProjectPromptsForm(forms.Form):
    """One optional text box per project-explanation prompt."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, question in PROJECT_PROMPTS:
            self.fields[key] = forms.CharField(
                label=question, required=False, max_length=MAX_NOTE_LENGTH,
                widget=forms.Textarea(attrs={"rows": 3}),
            )
