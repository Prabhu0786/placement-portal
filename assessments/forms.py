from django import forms

from content.models import Company, ContentStatus, Difficulty, Question, Topic


class PracticeSetupForm(forms.Form):
    type = forms.ChoiceField(
        required=False,
        label="Question type",
        choices=[("", "Any type")] + list(Question.QuestionType.choices),
    )
    topic = forms.ModelChoiceField(
        queryset=Topic.objects.all(), required=False, empty_label="Any topic", label="Topic"
    )
    difficulty = forms.ChoiceField(
        required=False,
        label="Difficulty",
        choices=[("", "Any difficulty")] + list(Difficulty.choices),
    )
    company = forms.ModelChoiceField(
        queryset=Company.objects.filter(status=ContentStatus.PUBLISHED),
        required=False,
        empty_label="Any company",
        label="Company",
    )
    count = forms.ChoiceField(
        label="Number of questions",
        choices=[("5", "5"), ("10", "10"), ("15", "15")],
        initial="5",
    )
