from django import forms
from django.utils import timezone

from content.models import Topic

from .models import WeeklyGoal
from .services import ACTIVE_STATUSES


class GoalForm(forms.ModelForm):
    target = forms.IntegerField(
        min_value=1, max_value=50, label="Questions to answer",
        help_text="How many questions in this topic you want to answer by the due date.",
    )

    class Meta:
        model = WeeklyGoal
        fields = ("topic", "due_date", "target")
        labels = {"topic": "Topic", "due_date": "Due date"}
        widgets = {"due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}
        help_texts = {
            "due_date": "Questions you answer in the 7 days up to this date count towards the goal.",
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["topic"].queryset = Topic.objects.order_by("subject", "name")
        self.fields["topic"].label_from_instance = lambda t: f"{t.subject} / {t.name}"

    def clean_due_date(self):
        due = self.cleaned_data["due_date"]
        if due < timezone.localdate():
            raise forms.ValidationError("Choose today or a later date.")
        return due

    def clean(self):
        cleaned = super().clean()
        topic, due = cleaned.get("topic"), cleaned.get("due_date")
        if topic and due and self.user is not None:
            duplicate = WeeklyGoal.objects.filter(
                user=self.user, topic=topic, due_date=due, status__in=ACTIVE_STATUSES
            ).exists()
            if duplicate:
                raise forms.ValidationError("You already have an open goal for this topic and date.")
        return cleaned

    def save(self, commit=True):
        goal = super().save(commit=False)
        goal.user = self.user
        if commit:
            goal.save()
        return goal
