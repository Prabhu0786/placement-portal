from django import forms

from content.models import Company, ContentStatus, Difficulty, Question, Topic

from .models import Assessment, AssessmentQuestion


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


class AssessmentForm(forms.ModelForm):
    questions = forms.ModelMultipleChoiceField(
        queryset=Question.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Questions",
        help_text="Only published multiple-choice questions can be used, so every answer can be scored automatically.",
    )
    marks_per_question = forms.IntegerField(
        min_value=1, max_value=10, initial=1, label="Marks for each question"
    )

    class Meta:
        model = Assessment
        fields = ("title", "type", "duration")
        labels = {"title": "Title", "type": "Type", "duration": "Duration (minutes)"}

    field_order = ["title", "type", "duration", "marks_per_question", "questions"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["questions"].queryset = (
            Question.objects.filter(status=ContentStatus.PUBLISHED)
            .exclude(options=[])
            .select_related("topic")
            .order_by("topic__subject", "topic__name", "id")
        )
        self.fields["questions"].label_from_instance = lambda q: f"[{q.topic.name}] {q.text[:80]}"
        self.locked = bool(self.instance.pk and self.instance.attempts.exists())
        if self.locked:
            # Students have already taken it: changing questions, marks or time would make
            # earlier scores meaningless, so only the title and type can change.
            for name in ("questions", "marks_per_question", "duration"):
                del self.fields[name]
        elif self.instance.pk:
            links = list(self.instance.assessmentquestion_set.all())
            self.fields["questions"].initial = [link.question_id for link in links]
            if links:
                self.fields["marks_per_question"].initial = links[0].marks

    def clean_duration(self):
        duration = self.cleaned_data["duration"]
        if not 1 <= duration <= 300:
            raise forms.ValidationError("Duration must be between 1 and 300 minutes.")
        return duration

    def save_questions(self, assessment):
        if self.locked:
            return
        selected = list(self.cleaned_data["questions"])  # already in subject/topic order
        marks = self.cleaned_data["marks_per_question"]
        assessment.assessmentquestion_set.exclude(question__in=selected).delete()
        for order, question in enumerate(selected, start=1):
            AssessmentQuestion.objects.update_or_create(
                assessment=assessment,
                question=question,
                defaults={"marks": marks, "display_order": order},
            )

    def save(self, commit=True):
        assessment = super().save(commit=commit)
        if commit:
            self.save_questions(assessment)
        return assessment
