from django import forms

from .models import Company, Difficulty, Resource, Topic


class ResourceFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Search")
    subject = forms.ChoiceField(required=False, label="Subject")
    topic = forms.ModelChoiceField(
        queryset=Topic.objects.all(), required=False, empty_label="All topics", label="Topic"
    )
    difficulty = forms.ChoiceField(
        required=False,
        label="Difficulty",
        choices=[("", "Any difficulty")] + list(Difficulty.choices),
    )
    type = forms.ChoiceField(
        required=False,
        label="Type",
        choices=[("", "All types")] + list(Resource.ResourceType.choices),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        subjects = sorted(set(Topic.objects.values_list("subject", flat=True)))
        self.fields["subject"].choices = [("", "All subjects")] + [(s, s) for s in subjects]


class ResourceForm(forms.ModelForm):
    url = forms.URLField(label="Link (URL)")

    class Meta:
        model = Resource
        fields = ("topic", "company", "title", "type", "url", "source")
        labels = {
            "company": "Company (optional)",
            "source": "Source (author or website)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["company"].empty_label = "Not specific to a company"


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ("name", "eligibility", "stages", "source")
        labels = {"source": "Source of this information"}
        help_texts = {
            "stages": "One recruitment stage per line, in order.",
            "source": "Required. For example: company careers page or placement-cell notice.",
        }
        widgets = {
            "eligibility": forms.Textarea(attrs={"rows": 3}),
            "stages": forms.Textarea(attrs={"rows": 5}),
        }


class TopicForm(forms.ModelForm):
    class Meta:
        model = Topic
        fields = ("subject", "name", "difficulty")
        help_texts = {"subject": "For example: Aptitude, Data Structures, Verbal."}
