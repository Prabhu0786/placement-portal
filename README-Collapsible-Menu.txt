PlacePort - Collapsible Vertical Navigation Menu

WHAT THIS UPDATE DOES
- Replaces the always-visible horizontal navigation list with a Menu (hamburger) button.
- Navigation links appear only after the user clicks Menu.
- The opened menu is vertically scrollable when there are more links than fit on screen.
- Works across roles because this is the shared accounts/base.html template.
- Menu closes when the user clicks outside, presses Escape, or follows a navigation link.
- Existing URLs, role-specific links, and logout form are preserved.

INSTALL
1. Extract this ZIP.
2. Copy accounts/templates/accounts/base.html from the extracted folder.
3. Paste/replace it in your project at the same path: placement-portal/accounts/templates/accounts/base.html
4. Run: python manage.py check
5. Run locally: python manage.py runserver and test Menu for Student, Faculty, TPO, and Admin accounts.
6. If it works, commit and push the changed file to GitHub; Vercel will deploy from your connected repository.

No database migration is required. This patch changes only the shared navigation template.
