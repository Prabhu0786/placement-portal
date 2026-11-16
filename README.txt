PlacePort account dropdown + persistent AI Assistant shortcut

FILES
- accounts/templates/accounts/base.html

INSTALL
1. Extract this ZIP.
2. Copy accounts/templates/accounts/base.html.
3. Replace the same file in your PlacePort project:
   placement-portal/accounts/templates/accounts/base.html
4. Run in the activated virtual environment:
   python manage.py check
   python manage.py runserver
5. Test:
   - Click the user name at the top-right: My Profile (students only) and Log out appear in the dropdown.
   - Confirm My Profile and Log out are no longer in the vertical Menu list.
   - Confirm the floating AI Assistant shortcut stays at the bottom-right on portal pages.
6. If local testing is successful, commit and push the changed file to GitHub; Vercel will deploy from the connected main branch.

No database migration is required. This update changes only the shared base template.
The AI Assistant route requires login, so guests who click it will be asked to log in by Django.
