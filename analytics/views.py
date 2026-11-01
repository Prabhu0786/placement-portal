from datetime import date, timedelta

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from accounts.models import User
from accounts.permissions import role_required

from . import reports, services


# ---------------------------------------------------------------- student pages
@role_required("Student")
def progress(request):
    """UC-08: accuracy, time, questions answered and trends."""
    return render(
        request,
        "analytics/progress.html",
        {"overview": services.student_overview(request.user)},
    )


@role_required("Student")
def weekly_report(request):
    current = services.monday_of(timezone.localdate())
    start = current
    raw = request.GET.get("week", "")
    try:
        start = services.monday_of(date.fromisoformat(raw))
    except ValueError:
        pass
    start = min(start, current)  # no reports for weeks that have not happened
    report = services.week_report(request.user, start)
    return render(
        request,
        "analytics/weekly.html",
        {
            "report": report,
            "previous_week": start - timedelta(days=7),
            "next_week": start + timedelta(days=7) if start < current else None,
            "is_current": start == current,
        },
    )


# ------------------------------------------------------------------- TPO pages
@role_required("TPO")
def reports_home(request):
    """UC-14: cohort progress (consenting students only)."""
    return render(request, "analytics/reports_home.html", {"report": reports.cohort_report()})


@role_required("TPO")
def report_student(request, pk):
    student = get_object_or_404(User, pk=pk, role__role_name="Student")
    consent = reports.has_consent(student)
    context = {"student": student, "consent": consent}
    if consent:
        context["overview"] = services.student_overview(student)
    return render(request, "analytics/report_student.html", context)


@role_required("TPO")
def report_export(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="cohort_report.csv"'
    reports.write_cohort_csv(response, reports.cohort_report())
    return response
