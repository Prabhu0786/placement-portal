"""Installs Phase 8 (notices and contests, applications, interview preparation, resume checklist and
project prompts) into the placement-portal project.

Run from the project folder (the one that contains manage.py):

    python install_phase8.py

It makes a few small, exact edits to existing files. If any file is not what the installer expects, it
stops BEFORE changing anything and tells you which one. Running it twice is safe.
"""
import os
import sys

ARROW = "\u2192"
EDITS = [
    ("content/models.py", None,
     "\n\nfrom .placement_models import ChecklistProgress, ContestParticipation, ProjectNote  # noqa: E402,F401\n",
     "from .placement_models import"),
    ("config/urls.py",
     '    path("", include("content.urls")),\n',
     '    path("", include("content.urls")),\n    path("", include("content.placement_urls")),\n',
     "content.placement_urls"),
    ("accounts/templates/accounts/base.html",
     "            <a href=\"{% url 'plan' %}\">Plan</a>\n",
     "            <a href=\"{% url 'plan' %}\">Plan</a>\n"
     "            <a href=\"{% url 'application_list' %}\">Applications</a>\n"
     "            <a href=\"{% url 'prepare_home' %}\">Prepare</a>\n",
     "application_list"),
    ("accounts/templates/accounts/base.html",
     "          <a href=\"{% url 'company_list' %}\">Companies</a>\n",
     "          <a href=\"{% url 'company_list' %}\">Companies</a>\n"
     "          <a href=\"{% url 'notice_list' %}\">Notices</a>\n",
     "notice_list"),
    ("accounts/templates/accounts/base.html",
     "            <a href=\"{% url 'reports_home' %}\">Reports</a>\n",
     "            <a href=\"{% url 'reports_home' %}\">Reports</a>\n"
     "            <a href=\"{% url 'manage_applications' %}\">Applications</a>\n",
     "manage_applications"),
    ("accounts/templates/accounts/dashboard.html",
     "      <a class=\"btn secondary\" href=\"{% url 'resume_analyzer' %}\">\n"
     f"        Analyze my resume {ARROW}\n"
     "      </a>\n"
     "    </article>\n",
     "      <a class=\"btn secondary\" href=\"{% url 'resume_analyzer' %}\">\n"
     f"        Analyze my resume {ARROW}\n"
     "      </a>\n"
     "    </article>\n"
     "\n"
     "    <!-- PHASE 8: PREPARATION, APPLICATIONS, NOTICES -->\n"
     "    {% load placement_tags %}\n"
     "    <article class=\"card\">\n"
     "      <div style=\"font-size:1.55rem;margin-bottom:8px\">\U0001F3AF</div>\n"
     "      <h2>Prepare for interviews</h2>\n"
     "      <p class=\"muted\">Interview questions with model answers, a resume checklist and project prompts.</p>\n"
     f"      <a class=\"btn secondary\" href=\"{{% url 'prepare_home' %}}\">Open preparation {ARROW}</a>\n"
     "    </article>\n"
     "\n"
     "    <article class=\"card\">\n"
     "      <div style=\"font-size:1.55rem;margin-bottom:8px\">\U0001F3E2</div>\n"
     "      <h2>My applications</h2>\n"
     "      <p class=\"muted\">Track companies, your eligibility and the status of each application.</p>\n"
     f"      <a class=\"btn secondary\" href=\"{{% url 'application_list' %}}\">Open tracker {ARROW}</a>\n"
     "    </article>\n"
     "\n"
     "    <article class=\"card\">\n"
     "      <div style=\"font-size:1.55rem;margin-bottom:8px\">\U0001F4E2</div>\n"
     "      <h2>Latest notices</h2>\n"
     "      {% latest_notices 3 as recent_notices %}\n"
     "      {% if recent_notices %}\n"
     "        <ul style=\"padding-left:18px;margin:0 0 10px\">\n"
     "          {% for n in recent_notices %}<li>{{ n.title }} <span class=\"muted\">({{ n.date|date:\"j M\" }})</span></li>{% endfor %}\n"
     "        </ul>\n"
     "      {% else %}\n"
     "        <p class=\"muted\">No notices yet.</p>\n"
     "      {% endif %}\n"
     f"      <a class=\"btn secondary\" href=\"{{% url 'notice_list' %}}\">All notices {ARROW}</a>\n"
     "    </article>\n",
     "placement_tags"),
    ("content/templates/content/manage_home.html",
     "  <div class=\"card\"><h2>Topics</h2>",
     "  <div class=\"card\"><h2>Notices and contests</h2><p class=\"muted\">Announcements and contests, and who registered.</p><a class=\"btn\" href=\"{% url 'manage_notices' %}\">Manage notices</a></div>\n"
     "  {% if user.is_tpo %}\n"
     "  <div class=\"card\"><h2>Applications</h2><p class=\"muted\">Applications from students who gave consent.</p><a class=\"btn\" href=\"{% url 'manage_applications' %}\">View applications</a></div>\n"
     "  {% endif %}\n"
     "  <div class=\"card\"><h2>Topics</h2>",
     "manage_notices"),
    ("content/templates/content/company_detail.html",
     "  <h1>{{ company.name }}</h1>\n",
     "  <h1>{{ company.name }}</h1>\n"
     "  {% if user.is_student %}\n"
     "    <form method=\"post\" action=\"{% url 'application_track' company.pk %}\" style=\"margin: 8px 0;\">{% csrf_token %}\n"
     "      <button class=\"btn secondary\" type=\"submit\">Track this company</button>\n"
     "    </form>\n"
     "  {% endif %}\n",
     "application_track"),
]

NEW_FILES = [
    "content/placement_models.py", "content/placement_services.py", "content/placement_forms.py",
    "content/placement_views.py", "content/placement_urls.py",
    "content/templatetags/__init__.py", "content/templatetags/placement_tags.py",
    "content/management/commands/seed_interview_questions.py",
    "content/templates/content/placement/notice_list.html",
    "content/templates/content/placement/manage_notices.html",
    "content/templates/content/placement/application_list.html",
    "content/templates/content/placement/manage_applications.html",
    "content/templates/content/placement/prepare_home.html",
    "content/templates/content/placement/interview_prep.html",
    "content/templates/content/placement/resume_checklist.html",
    "content/templates/content/placement/project_list.html",
    "content/templates/content/placement/project_prepare.html",
    "content/test_placement.py",
    "content/migrations/0004_checklistprogress_contestparticipation_projectnote.py",
]


def fail(message):
    print("\nSTOPPED. Nothing was changed.\n" + message)
    sys.exit(1)


def main():
    if not os.path.exists("manage.py"):
        fail("Run this from the project folder (the one that contains manage.py).")
    missing = [p for p in NEW_FILES if not os.path.exists(p)]
    if missing:
        fail("These files should have been copied into the project first:\n  " + "\n  ".join(missing))
    pending, report = {}, []
    for path, old, new, marker in EDITS:
        if not os.path.exists(path):
            fail(f"Cannot find {path}.")
        if path in pending:
            text, newline = pending[path]
        else:
            with open(path, "r", encoding="utf-8", newline="") as handle:
                raw = handle.read()
            newline = "\r\n" if "\r\n" in raw else "\n"
            text = raw.replace("\r\n", "\n")
        if marker in text:
            report.append(f"already done: {path} ({marker})")
        elif old is None:
            text = text.rstrip("\n") + new
            report.append(f"will edit:    {path}")
        elif text.count(old) != 1:
            fail(f"{path} is different from what this installer expects (it was probably edited).\n"
                 f"Could not find this text exactly once:\n{old}")
        else:
            text = text.replace(old, new, 1)
            report.append(f"will edit:    {path}")
        pending[path] = (text, newline)
    for path, (text, newline) in pending.items():
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text.replace("\n", newline))
    print("\n".join(report))
    print("\nDone. Next: python manage.py migrate, then python manage.py test content")


if __name__ == "__main__":
    main()
