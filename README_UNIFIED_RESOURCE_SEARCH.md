# Unified Resource Search — No Google API Key Required

This patch extends the existing `content` app and student dashboard. It does not change models, create migrations, or remove existing resource-management views.

## Files in this patch

- `content/views.py` → `content/views.py`
- `content/templates/content/resource_list.html` → `content/templates/content/resource_list.html`
- `templates/dashboard.html` → replace your existing student dashboard template (use the exact path of your current file if it differs).

`content/urls.py` does not need changes. The existing `resources/` route and `resource_list` URL name are reused.

## External sources — no Google credentials required

- Existing published portal resources are searched from the Django database.
- GitHub public repository search uses GitHub's unauthenticated public API. It is subject to GitHub's public rate limits.
- YouTube Data API search uses `YOUTUBE_API_KEY` if it is already configured in your portal. If it is absent or unavailable, the page links directly to YouTube search.
- MDN, freeCodeCamp, NPTEL, SWAYAM and GeeksforGeeks are offered as direct site-search links.
- PDF search opens a Google web search for the query with `filetype:pdf`; it does not use the Google Programmable Search API or an API key. Students should verify the publisher's permission before downloading or sharing a document.

No `GOOGLE_CSE_CX` or `GOOGLE_CSE_API_KEY` variables are needed. Do not add placeholder values for them.

## Behaviour and safeguards

- Only published internal resources are searched.
- External links open on their original websites; the portal does not download third-party PDFs.
- API results are cached for 10 minutes.
- GitHub and YouTube requests have short timeouts and safe failure handling.
- No database migration is required.

## Test locally

```powershell
python manage.py check
python manage.py runserver
```

Log in as a student and search for `Java interview questions`. Try All sources, PDF documents, YouTube videos and GitHub repositories.

## Deploy

```powershell
git add content/views.py content/templates/content/resource_list.html templates/dashboard.html
git commit -m "Add unified resource search without Google API credentials"
git push origin main
```

If your dashboard template is stored elsewhere, replace the path in the `git add` command with its actual path.
