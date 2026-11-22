"""Fixes two things found while reviewing the project. Run from the folder that contains manage.py:

    python fix_existing_issues.py

1. REAL BUG: /practice/?topic=5 redirected to the Practice & Assessments page but dropped
   "?topic=5", so the "Practise this topic" buttons no longer preselected the topic.
2. Four old tests still expected the Practice page to be a page of its own, so they failed.

Safe to run twice. If a file is not what it expects, it stops before changing anything.
"""
import os
import sys

EDITS = [
    (
        "assessments/views.py",
        '    # Legacy route: Practice now lives inside the unified Practice & Assessments page.\n'
        '    return redirect("assessment_list")\n',
        '    # Legacy route: Practice now lives inside the unified Practice & Assessments page.\n'
        '    # Keep any query string (for example ?topic=5) so "Practise this topic" still preselects the topic.\n'
        '    url = reverse("assessment_list")\n'
        '    if request.GET:\n'
        '        url = f"{url}?{request.GET.urlencode()}"\n'
        '    return redirect(url)\n',
        "Keep any query string",
    ),
    (
        "assessments/tests.py",
        '        self.client.logout(); self.login(self.student)\n'
        '        self.assertEqual(self.client.get(reverse("practice_home")).status_code, 200)\n',
        '        self.client.logout(); self.login(self.student)\n'
        '        # practice_home is now a redirect to the unified Practice & Assessments page\n'
        '        self.assertRedirects(self.client.get(reverse("practice_home")), reverse("assessment_list"))\n',
        "practice_home is now a redirect to the unified",
    ),
    (
        "assessments/tests.py",
        '        response = self.start()\n'
        '        self.assertRedirects(response, reverse("practice_home"))\n'
        '        self.assertEqual(Attempt.objects.count(), 0)\n',
        '        response = self.start()\n'
        '        # practice_home itself redirects on, so only check where this response sends the student\n'
        '        self.assertRedirects(response, reverse("practice_home"), fetch_redirect_response=False)\n'
        '        self.assertEqual(Attempt.objects.count(), 0)\n',
        "practice_home itself redirects on",
    ),
    (
        "assessments/tests.py",
        '        self.assertContains(self.client.get(reverse("practice_home")), "Continue")\n',
        '        # the practice history now appears on the unified Practice & Assessments page\n'
        '        self.assertContains(self.client.get(reverse("assessment_list")), "Continue")\n',
        "practice history now appears on the unified",
    ),
    (
        "analytics/tests.py",
        '        page = self.client.get(reverse("practice_home"), {"topic": self.t2.pk})\n',
        '        # practice_home redirects to the unified page and must keep ?topic=\n'
        '        page = self.client.get(reverse("practice_home"), {"topic": self.t2.pk}, follow=True)\n',
        "must keep ?topic=",
    ),
]


def fail(message):
    print("\nSTOPPED. Nothing was changed.\n" + message)
    sys.exit(1)


def main():
    if not os.path.exists("manage.py"):
        fail("Run this from the project folder (the one that contains manage.py).")
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
            report.append(f"already done: {path}")
        elif text.count(old) != 1:
            fail(f"{path} is different from what this script expects (it was probably edited).\nCould not find exactly once:\n{old}")
        else:
            text = text.replace(old, new, 1)
            report.append(f"will edit:    {path}")
        pending[path] = (text, newline)
    for path, (text, newline) in pending.items():
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text.replace("\n", newline))
    print("\n".join(report))
    print("\nDone. Now run: python manage.py test accounts content assessments analytics planning ai_assistant")


if __name__ == "__main__":
    main()
