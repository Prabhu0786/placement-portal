"""Installs the AI Mock Interview into the placement-portal project.

Run from the project folder (the one that contains manage.py):

    python install_mock_interview.py

It makes a few small, exact edits to existing files. If any file is not what the installer
expects, it stops BEFORE changing anything and tells you which one. Running it twice is safe.
To undo everything, use:  git checkout -- .   (and delete the new files it listed)
"""
import os
import sys

EDITS = [
    # (file, text to find, text to put instead, marker that shows the edit is already done)
    (
        "accounts/models.py",
        "    consent_given = models.BooleanField(default=False)\n"
        "    consent_date = models.DateTimeField(null=True, blank=True)\n",
        "    consent_given = models.BooleanField(default=False)\n"
        "    consent_date = models.DateTimeField(null=True, blank=True)\n"
        "    # Separate consent for sending text to an outside AI service (BR-14).\n"
        "    ai_consent_given = models.BooleanField(default=False)\n"
        "    ai_consent_date = models.DateTimeField(null=True, blank=True)\n",
        "ai_consent_given",
    ),
    (
        "ai_assistant/models.py",
        None,  # append
        "\n\nfrom .mock_models import MockInterview, MockInterviewTurn  # noqa: E402,F401\n",
        "from .mock_models import",
    ),
    (
        "ai_assistant/urls.py",
        "from django.urls import path\n",
        "from django.urls import include, path\n",
        "from django.urls import include, path",
    ),
    (
        "ai_assistant/urls.py",
        '    path("clear/", views.clear_chat, name="ai_clear_chat"),\n',
        '    path("clear/", views.clear_chat, name="ai_clear_chat"),\n'
        '    path("mock-interview/", include("ai_assistant.mock_urls")),\n',
        "ai_assistant.mock_urls",
    ),
    (
        "accounts/templates/accounts/base.html",
        "            <a href=\"{% url 'resume_analyzer' %}\">Resume Analyzer</a>\n",
        "            <a href=\"{% url 'resume_analyzer' %}\">Resume Analyzer</a>\n"
        "            <a href=\"{% url 'ai_mock_home' %}\">Mock Interview</a>\n",
        "ai_mock_home",
    ),
    (
        "accounts/templates/accounts/dashboard.html",
        "      <a class=\"btn secondary\" href=\"{% url 'resume_analyzer' %}\">\n"
        "        Analyze my resume \u2192\n"
        "      </a>\n"
        "    </article>\n",
        "      <a class=\"btn secondary\" href=\"{% url 'resume_analyzer' %}\">\n"
        "        Analyze my resume \u2192\n"
        "      </a>\n"
        "    </article>\n"
        "\n"
        "    <!-- AI MOCK INTERVIEW -->\n"
        "    <article class=\"card\">\n"
        "      <div style=\"font-size:1.55rem;margin-bottom:8px\">\U0001F3A4</div>\n"
        "\n"
        "      <h2>AI Mock Interview</h2>\n"
        "\n"
        "      <p class=\"muted\">\n"
        "        Practise interview questions one at a time and get feedback\n"
        "        on every answer, plus a short summary at the end.\n"
        "      </p>\n"
        "\n"
        "      <a class=\"btn secondary\" href=\"{% url 'ai_mock_home' %}\">\n"
        "        Start a mock interview \u2192\n"
        "      </a>\n"
        "    </article>\n",
        "ai_mock_home",
    ),
]

NEW_FILES = [
    "ai_assistant/gemini_client.py",
    "ai_assistant/mock_models.py",
    "ai_assistant/mock_services.py",
    "ai_assistant/mock_forms.py",
    "ai_assistant/mock_views.py",
    "ai_assistant/mock_urls.py",
    "ai_assistant/templates/ai_assistant/_mock_styles.html",
    "ai_assistant/templates/ai_assistant/_mock_feedback.html",
    "ai_assistant/templates/ai_assistant/mock_home.html",
    "ai_assistant/templates/ai_assistant/mock_run.html",
    "ai_assistant/templates/ai_assistant/mock_report.html",
    "ai_assistant/test_mock_interview.py",
    "ai_assistant/migrations/0003_mockinterview_mockinterviewturn.py",
    "accounts/migrations/0003_studentprofile_ai_consent_date_and_more.py",
]


def fail(message):
    print("\nSTOPPED. Nothing was changed.\n" + message)
    sys.exit(1)


def main():
    if not os.path.exists("manage.py"):
        fail("Run this from the project folder (the one that contains manage.py).")
    missing = [path for path in NEW_FILES if not os.path.exists(path)]
    if missing:
        fail("These files should have been copied into the project first:\n  " + "\n  ".join(missing))

    pending = {}  # path -> (new text, newline style)
    report = []
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
            pending[path] = (text, newline)
            continue
        if old is None:
            text = text.rstrip("\n") + new
        else:
            if text.count(old) != 1:
                fail(
                    f"{path} is different from what this installer expects (it was probably edited).\n"
                    f"Could not find this text exactly once:\n{old}"
                )
            text = text.replace(old, new, 1)
        pending[path] = (text, newline)
        report.append(f"will edit:    {path}")

    for path, (text, newline) in pending.items():
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text.replace("\n", newline))

    print("\n".join(report))
    print("\nDone. Next: python manage.py migrate, then python manage.py test ai_assistant")


if __name__ == "__main__":
    main()
