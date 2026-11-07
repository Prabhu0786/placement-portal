"""Approved sources for the automatic learning-resource collector.

Only add feeds and direct resources after checking the source's terms.
For PDFs, add an explicit licence name and a URL to the licence/permission.
The collector stores links and metadata; it does not copy copyrighted files.
"""

RESOURCE_SOURCES = [
    {
        "name": "freeCodeCamp",
        "domain": "freecodecamp.org",
        "feed_url": "https://www.freecodecamp.org/news/rss/",
        "subject": "Programming",
        "topic": "Programming Tutorials",
        "language": "en",
        "enabled": True,
    },
    {
        "name": "MDN Web Docs",
        "domain": "developer.mozilla.org",
        "feed_url": "https://developer.mozilla.org/en-US/blog/rss.xml",
        "subject": "Web Development",
        "topic": "HTML CSS JavaScript",
        "language": "en",
        "enabled": True,
    },
]

# Add hand-picked article/course pages here when a site has no suitable feed.
# The URL must be HTTPS and on the listed domain.
CURATED_RESOURCES = [
    # {
    #     "name": "Example Learning Site",
    #     "domain": "example.org",
    #     "title": "Introduction to Data Structures",
    #     "url": "https://example.org/data-structures",
    #     "subject": "Data Structures",
    #     "topic": "Introduction",
    #     "language": "en",  # en, hi, other, unknown
    #     "type": "article",  # article or link
    #     "enabled": True,
    # },
]

# Only add PDFs after verifying that the licence explicitly permits sharing/linking.
# Do not put ordinary copyrighted PDFs here.
LICENSED_PDF_RESOURCES = [
    # {
    #     "name": "Open textbook publisher",
    #     "domain": "example.org",
    #     "title": "Open Data Structures Textbook",
    #     "url": "https://example.org/files/data-structures.pdf",
    #     "subject": "Data Structures",
    #     "topic": "Data Structures Notes",
    #     "language": "en",
    #     "license": "CC BY 4.0",
    #     "license_url": "https://creativecommons.org/licenses/by/4.0/",
    #     "enabled": True,
    # },
]
