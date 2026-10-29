from django import forms

from .models import Company, Difficulty, Question, Resource, Topic


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


class QuestionForm(forms.ModelForm):
    options_text = forms.CharField(
        required=False,
        label="Answer options (multiple choice)",
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text=(
            "One option per line. Leave empty for an open question "
            "(coding, technical or interview), which is not scored automatically."
        ),
    )

    class Meta:
        model = Question
        fields = ("topic", "company", "type", "difficulty", "text", "answer", "explanation")
        labels = {
            "company": "Company (optional)",
            "text": "Question",
            "answer": "Correct answer (or model answer)",
        }
        help_texts = {
            "answer": "For multiple choice, type or copy the correct option exactly.",
        }
        widgets = {
            "text": forms.Textarea(attrs={"rows": 4}),
            "answer": forms.Textarea(attrs={"rows": 3}),
            "explanation": forms.Textarea(attrs={"rows": 3}),
        }

    field_order = [
        "topic", "company", "type", "difficulty", "text",
        "options_text", "answer", "explanation",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["company"].empty_label = "Not specific to a company"
        if self.instance and self.instance.pk and self.instance.options:
            self.fields["options_text"].initial = "\n".join(self.instance.options)

    def clean(self):
        cleaned = super().clean()
        options = [line.strip() for line in cleaned.get("options_text", "").splitlines() if line.strip()]
        seen = {" ".join(o.split()).casefold() for o in options}
        if options:
            if len(options) < 2:
                self.add_error("options_text", "Give at least two options, one per line.")
            elif len(seen) != len(options):
                self.add_error("options_text", "Options must all be different.")
            else:
                answer = " ".join(cleaned.get("answer", "").split()).casefold()
                match = next((o for o in options if " ".join(o.split()).casefold() == answer), None)
                if match is None:
                    self.add_error("answer", "For a multiple-choice question the answer must match one of the options.")
                else:
                    cleaned["answer"] = match
        self.cleaned_options = options
        return cleaned

    def save(self, commit=True):
        self.instance.options = getattr(self, "cleaned_options", [])
        return super().save(commit)
