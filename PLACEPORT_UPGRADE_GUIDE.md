# PlacePort incremental upgrade

This update preserves the existing Django project and adds a focused AI resume-review workflow plus student-context awareness in the existing AI assistant. It does not replace the current dashboards, assessments, analytics, planning, resources, roles, or placement workflows.

## What is new

1. **AI Resume Analyzer** at `/ai-assistant/resume-analyzer/` (Student role only).
   - Accepts PDF, DOCX and TXT up to 5 MB.
   - Optional target role and job description comparison.
   - Returns strengths, improvements, missing sections, suggested bullet rewrites, skills found and next steps.
   - Stores the structured review and filename, not the uploaded file or extracted resume text.
   - The score is a heuristic document-quality indicator, not an official ATS score or selection prediction.
2. **Context-aware AI Assistant**.
   - Adds the currently signed-in student's own profile skills, target roles and recorded assessment summary to the AI prompt when available.
   - Keeps existing chat history, streaming, retry, attachment upload, language and assistant modes.
3. **Student navigation link** to Resume Analyzer.

## Before updating

You have two archive choices: `PlacePort_AI_Upgrade_Patch.zip` contains only the added/modified files and can be extracted directly into your existing project root (the folder containing `manage.py`); `PlacePort_Updated_Project.zip` contains the complete source tree in a `placement-portal/` folder. For the least disruptive update, use the patch archive.

1. Make a full backup of your current project and production database.
2. Do not overwrite your `.env` file or change your Vercel environment variables.
3. If your project is connected to GitHub, commit your current working version first.
4. Extract this updated project into a separate folder first and compare it with your existing source if you have made local changes after the uploaded ZIP.

## Local update steps

1. Extract `PlacePort_AI_Upgrade_Patch.zip` directly into your existing project root and allow the listed files to be replaced. Do not extract it into a new nested `placement-portal` folder.
2. Keep your existing `.env`, production environment variables and database unchanged.

From the project root (the folder containing `manage.py`):

```bash
# Activate your existing virtual environment first
pip install -r requirements.txt
python manage.py check
python manage.py migrate
python manage.py test ai_assistant
python manage.py test
```

No new third-party package is required for this feature; `pypdf` and `python-docx` are already listed in requirements.

Run locally:

```bash
python manage.py runserver
```

Log in with a Student account and open:

`http://127.0.0.1:8000/ai-assistant/resume-analyzer/`

## Deploying to Vercel

1. Merge/copy the changed files into your existing repository. Keep your production `.env` and Vercel environment variables; never upload `.env` to GitHub.
2. Ensure these Vercel environment variables remain configured:
   - `SECRET_KEY`
   - `DATABASE_URL`
   - `GEMINI_API_KEY`
   - `GEMINI_MODEL` (optional; defaults to the existing project default)
   - `GEMINI_FALLBACK_MODEL` (optional)
3. Deploy the updated code.
4. Apply the migration against the same production database used by the portal:

```bash
python manage.py migrate
```

Run this from a trusted local environment configured with the production `DATABASE_URL`, or through your established deployment/release process. Do not expose the database URL in logs or screenshots.

5. Verify the deployed portal:
   - Student login still works.
   - Existing AI chat, retry and file attachment still work.
   - Resume Analyzer page loads for Students.
   - Faculty/TPO accounts cannot access the Student-only analyzer.
   - A valid PDF/DOCX/TXT produces a saved review.
   - Invalid file types and files over 5 MB are rejected.

## Files changed

- `ai_assistant/models.py`
- `ai_assistant/migrations/0002_resumereview.py` (new)
- `ai_assistant/views.py`
- `ai_assistant/urls.py`
- `ai_assistant/admin.py`
- `ai_assistant/templates/ai_assistant/resume_analyzer.html` (new)
- `accounts/templates/accounts/base.html`

## Security and privacy notes

- The uploaded resume is read in memory and is not saved to the media directory.
- The extracted resume text is sent to the configured Gemini API for analysis. Ensure this use is covered by your student privacy notice and applicable provider settings.
- The database retains the generated report and uploaded filename. Define a retention period before broad institutional rollout.
- The review is visible only to its owner through the Student-only page; administrators with database/admin access may still access stored report data.
- AI feedback can be wrong. Students must verify all suggested edits and must not add untrue claims.
