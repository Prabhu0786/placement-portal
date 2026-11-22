from django import forms

from content.models import Topic

from . import mock_services as services
from .mock_models import MockInterview


class MockSetupForm(forms.Form):
    source = forms.ChoiceField(
        label="Where should the questions come from?",
        choices=MockInterview.Source.choices,
        initial=MockInterview.Source.BANK,
        widget=forms.RadioSelect,
    )
    topic = forms.ModelChoiceField(
        label="Interview topic (question bank)",
        queryset=Topic.objects.none(),
        required=False,
        empty_label="Any interview topic",
    )
    ai_type = forms.ChoiceField(
        label="Interview type (AI-generated questions)",
        choices=[("", "Choose a type")] + list(services.AI_TYPES.items()),
        required=False,
    )
    difficulty = forms.ChoiceField(
        label="Difficulty (AI-generated questions)",
        choices=[("easy", "Easy"), ("medium", "Medium"), ("hard", "Hard")],
        initial="medium",
    )
    count = forms.ChoiceField(
        label="Number of questions",
        choices=[(str(n), str(n)) for n in services.COUNT_CHOICES],
        initial="5",
    )
    target_role = forms.CharField(
        label="Target role (optional)", max_length=160, required=False,
        help_text="For example: Graduate Software Developer.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["topic"].queryset = services.bank_topics()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("source") == MockInterview.Source.AI and not cleaned.get("ai_type"):
            self.add_error("ai_type", "Choose an interview type for AI-generated questions.")
        return cleaned
