PLACEPORT ADDITIVE UPGRADE (from supplied placement-portal (2).zip)

Includes:
- Global single-row horizontally scrollable nav in accounts/templates/accounts/base.html
- Student-only floating AI Assistant link (opens existing AI chat)
- AI-generated topic mock tests using existing Assessment, Question, Attempt, Response models
- Uses existing scoring, server timer, feedback and history; no schema changes
- Existing OTP password reset files are untouched and retained in your original project

COPY these 5 files to their corresponding locations:
accounts/templates/accounts/base.html
assessments/urls.py
assessments/views.py
assessments/ai_mock_views.py  (NEW)
assessments/templates/assessments/assessment_list.html

Then run:
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test assessments
python manage.py runserver

Visit /assessments/ as a Student, enter a topic and generate a mock test.
Uses existing GEMINI_API_KEY and GEMINI_MODEL environment variables.
The server generates questions on demand; model access can fail or incur API costs.
No migrations needed for this update.

SECURITY/OPERATION NOTES:
- Generated tests are draft/private to their creator; existing published tests remain available.
- Generated questions are saved as drafts and are not added to published practice bank.
- Rate limit uses Django cache; configure a shared cache or edge-level throttling for robust multi-instance limits.
- AI questions can be wrong; generated questions should not be used as high-stakes assessments without review.
- Floating button links to existing assistant page; it is not an embedded popup.
- For production, ensure Vercel runs migrations for earlier OTP changes; this update has none.

PUSH:
git add accounts/templates/accounts/base.html assessments/urls.py assessments/views.py assessments/ai_mock_views.py assessments/templates/assessments/assessment_list.html
git commit -m "Add AI mock tests, global scrollable navigation and AI shortcut"
git push origin main
