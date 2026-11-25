"""Rules for notices and contests, company applications, the resume checklist and project prompts."""
from django.utils import timezone

from accounts.models import StudentProfile

from .models import Application, ContentStatus, NoticeContest

# ====================================================================== applications
AppStatus = Application.ApplicationStatus
Eligibility = Application.EligibilityStatus

# State diagram: Interested, Eligible, Applied, Shortlisted, Rejected, Selected, Withdrawn.
TRANSITIONS = {
    "interested": {"eligible", "applied", "withdrawn"},
    "eligible": {"applied", "withdrawn"},
    "applied": {"shortlisted", "rejected", "withdrawn"},
    "shortlisted": {"selected", "rejected", "withdrawn"},
    "rejected": set(),
    "selected": set(),
    "withdrawn": set(),
}
FINAL = {"rejected", "selected", "withdrawn"}
BUTTON_ORDER = ["applied", "shortlisted", "selected", "rejected", "withdrawn"]
LABELS = {
    "applied": "I have applied",
    "shortlisted": "Shortlisted",
    "selected": "Selected",
    "rejected": "Rejected",
    "withdrawn": "Withdraw",
}
# "Eligible" is reached by recording eligibility, so it has no button of its own.
STUDENT_TARGETS = {"applied", "shortlisted", "selected", "rejected", "withdrawn"}
TPO_TARGETS = {"shortlisted", "selected", "rejected"}  # recruitment updates the TPO receives


class ApplicationError(ValueError):
    """A problem the person can fix. The message is shown to them."""


def available_actions(application, role):
    """Buttons [(target, label)] this role may press for the application's current status."""
    allowed = STUDENT_TARGETS if role == "Student" else TPO_TARGETS if role == "TPO" else set()
    return [
        (to, LABELS[to])
        for to in BUTTON_ORDER
        if to in TRANSITIONS[application.application_status] and to in allowed
    ]


def change_status(application, to, role="Student"):
    if to not in dict(available_actions(application, role)):
        raise ApplicationError("That change is not allowed for this application.")
    if to == "applied" and application.eligibility_status == Eligibility.NOT_ELIGIBLE:
        raise ApplicationError(
            "You marked yourself as not eligible for this company. Change the eligibility first if that is wrong."
        )
    application.application_status = to
    application.save(update_fields=["application_status"])


def set_eligibility(application, value):
    """Record the eligibility check. Keeps the status in step while the application is still open."""
    if value not in Eligibility.values:
        raise ApplicationError("Choose Not checked, Eligible or Not eligible.")
    if application.application_status in FINAL:
        raise ApplicationError("This application is closed, so its eligibility can no longer be changed.")
    application.eligibility_status = value
    if value == Eligibility.ELIGIBLE and application.application_status == AppStatus.INTERESTED:
        application.application_status = AppStatus.ELIGIBLE
    elif value != Eligibility.ELIGIBLE and application.application_status == AppStatus.ELIGIBLE:
        application.application_status = AppStatus.INTERESTED
    application.save(update_fields=["eligibility_status", "application_status"])


def consenting_student_ids():
    """Students whose data the TPO may see (BR-10, BR-14)."""
    return set(
        StudentProfile.objects.filter(consent_given=True, user__role__role_name="Student").values_list(
            "user_id", flat=True
        )
    )


# ========================================================================== contests
def can_register(contest, today=None):
    today = today or timezone.localdate()
    return (
        contest.kind == NoticeContest.Kind.CONTEST
        and contest.status == ContentStatus.PUBLISHED
        and contest.date >= today
    )


# ============================================================= resume and projects
RESUME_CHECKLIST = [
    ("contact", "Contact details", "Name, phone number, a professional email, and a LinkedIn or GitHub link are at the top."),
    ("length", "Length", "One page for a fresher, unless you have a lot of real experience."),
    ("summary", "Short summary", "Two lines on the role you want and your strongest skills, written for the job you are applying to."),
    ("education", "Education", "Degree, college, year and CGPA or percentage, newest first."),
    ("skills", "Skills", "Grouped (languages, databases, tools). List only what you could talk about in an interview."),
    ("projects", "Projects", "Your two or three best, each with what it does, the technology used and your own part."),
    ("results", "Results", "Honest numbers where you have them, such as 'handles 200 users' or 'cut load time by 30%'."),
    ("verbs", "Action verbs", "Bullets start with verbs such as built, designed, tested or improved."),
    ("certificates", "Certificates and achievements", "Only relevant ones, with a link where possible."),
    ("links", "Working links", "Every GitHub or project link opens, and each repository has a clear README."),
    ("proofread", "Proofreading", "No spelling or grammar mistakes. Ask a friend or faculty member to read it."),
    ("format", "Format", "Plain, consistent fonts and spacing, saved as a PDF named like Name_Resume.pdf."),
    ("honesty", "Honesty", "Everything on it is true, and you can explain every line."),
]

PROJECT_PROMPTS = [
    ("problem", "What problem does this project solve, and for whom?"),
    ("role", "What exactly did YOU build or decide? Separate your work from the team's."),
    ("tech", "Which technologies did you use, and why did you choose them?"),
    ("challenge", "What was the hardest problem you faced, and how did you solve it?"),
    ("result", "What was the result? Any numbers, feedback or lessons learned?"),
    ("improve", "If you had two more weeks, what would you improve?"),
]
MAX_NOTE_LENGTH = 2000
