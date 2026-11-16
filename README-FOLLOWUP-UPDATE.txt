PLACEPORT FOLLOW-UP UPDATE
==========================

This update addresses your requested changes:
1. Increase AI mock-test size to 10, 15, 20, 30, 40 or 50 questions.
2. Combine Practice and Assessments into one student navigation destination and one landing page.
3. Add a clearly visible horizontal scrollbar to the global navigation, plus desktop left/right scroll buttons. On mobile, use touch scrolling and the visible scrollbar.
4. Increase regular question-bank practice choices up to 50 questions.

COPY the six files into the same relative paths in your project:
- accounts/templates/accounts/base.html
- assessments/ai_mock_views.py (new)
- assessments/views.py
- assessments/urls.py
- assessments/forms.py
- assessments/templates/assessments/assessment_list.html

Do not overwrite the OTP password reset files. This package does not include or modify them.
No database migration is expected.

Then run:
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test assessments
python manage.py runserver

Test as a Student:
- Open the unified Practice & Assessments navigation item.
- Try question-bank practice with larger question counts.
- Generate an AI mock test with 20/30/40/50 questions.
- Confirm generated tests appear in the existing timed assessment list and use the existing timer, autosave, scoring and result flow.
Test each role's navigation; the shared base template provides the same scroll controls while preserving role-specific links.

Important:
- AI generation uses your existing GEMINI_API_KEY and GEMINI_MODEL.
- Larger generations can take longer and consume more API quota. If the configured Gemini model's output limit is too small, 40/50-question generation may fail; the view handles this with a friendly error. Consider 20 or 30 as a practical default.
- AI-generated questions can contain mistakes and should not be treated as verified high-stakes exam material.
- No production push is performed by this package. Test locally before committing.
