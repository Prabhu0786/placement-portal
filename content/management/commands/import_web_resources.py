
"""
Import approved educational articles and explicitly licensed PDF links.

Sources are controlled by content/resource_sources.py.
This command stores metadata and original URLs; it does not download
or republish article/PDF files.
"""

import re
import xml.etree.ElementTree as ET

from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.core.management.base import BaseCommand
from django.db.models import Q

from content.models import (
    ContentStatus,
    Difficulty,
    Resource,
    Topic,
)

from content.resource_sources import (
    CURATED_RESOURCES,
    LICENSED_PDF_RESOURCES,
    RESOURCE_SOURCES,
)


MAX_FEED_BYTES = 5 * 1024 * 1024
MAX_FEED_ITEMS = 30

USER_AGENT = (
    "PlacementPortalResourceCollector/1.0 "
    "(educational resource index)"
)


# --------------------------------------------------
# HTML DESCRIPTION CLEANER
# --------------------------------------------------

class TextExtractor(HTMLParser):

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        value = data.strip()

        if value:
            self.parts.append(value)

    def text(self):
        return re.sub(
            r"\s+",
            " ",
            " ".join(self.parts)
        ).strip()


def strip_markup(value):

    parser = TextExtractor()

    try:
        parser.feed(value or "")
        return parser.text()

    except (ValueError, TypeError):
        return ""


# --------------------------------------------------
# XML HELPERS
# --------------------------------------------------

def tag_name(tag):
    return tag.rsplit("}", 1)[-1].lower()


def child_text(element, wanted):

    for child in element:

        if tag_name(child.tag) == wanted:
            return "".join(child.itertext()).strip()

    return ""


# --------------------------------------------------
# URL VALIDATION
# --------------------------------------------------

def approved_https_url(url, domain):
    """
    Require HTTPS and an exact approved host or its subdomain.
    """

    try:

        parsed = urlparse((url or "").strip())

        host = (
            parsed.hostname or ""
        ).lower().rstrip(".")

        allowed = (
            domain or ""
        ).lower().strip().rstrip(".")

        return bool(
            parsed.scheme == "https"
            and host
            and allowed
            and (
                host == allowed
                or host.endswith("." + allowed)
            )
            and not parsed.username
            and not parsed.password
            and parsed.port in (None, 443)
        )

    except (TypeError, ValueError):

        return False


class DomainRedirectHandler(HTTPRedirectHandler):
    """
    Prevent a configured feed from redirecting
    to an unrelated host.
    """

    def __init__(self, allowed_domain):

        super().__init__()
        self.allowed_domain = allowed_domain

    def redirect_request(
        self,
        req,
        fp,
        code,
        msg,
        headers,
        newurl
    ):

        if not approved_https_url(
            newurl,
            self.allowed_domain
        ):

            raise ValueError(
                "Feed redirect left the approved HTTPS domain."
            )

        return super().redirect_request(
            req,
            fp,
            code,
            msg,
            headers,
            newurl
        )


# --------------------------------------------------
# FETCH RSS / ATOM FEED
# --------------------------------------------------

def fetch_feed(feed_url, domain):

    if not approved_https_url(feed_url, domain):

        raise ValueError(
            "Feed URL is not on its approved HTTPS domain."
        )

    request = Request(
        feed_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "application/rss+xml, "
                "application/atom+xml, "
                "application/xml, text/xml"
            ),
        },
    )

    opener = build_opener(
        DomainRedirectHandler(domain)
    )

    with opener.open(
        request,
        timeout=25
    ) as response:

        final_url = response.geturl()

        if not approved_https_url(
            final_url,
            domain
        ):

            raise ValueError(
                "Final feed URL is not on the approved domain."
            )

        data = response.read(
            MAX_FEED_BYTES + 1
        )

    if len(data) > MAX_FEED_BYTES:

        raise ValueError(
            "Feed exceeded the 5 MB size limit."
        )

    return data


# --------------------------------------------------
# PARSE RSS AND ATOM
# --------------------------------------------------

def parse_feed(data, feed_url):

    root = ET.fromstring(data)

    results = []

    for entry in root.iter():

        if tag_name(entry.tag) not in (
            "item",
            "entry"
        ):
            continue

        title = child_text(
            entry,
            "title"
        )

        link = ""

        for child in entry:

            if tag_name(child.tag) == "link":

                href = (
                    child.attrib.get("href") or ""
                ).strip()

                rel = (
                    child.attrib.get("rel") or "alternate"
                ).lower()

                text = (
                    child.text or ""
                ).strip()

                if href and rel in ("alternate", ""):
                    link = urljoin(feed_url, href)
                    break

                if text:
                    link = urljoin(feed_url, text)

        description = (
            child_text(entry, "description")
            or child_text(entry, "summary")
            or child_text(entry, "content")
        )

        if title and link:

            results.append({
                "title": strip_markup(title),
                "url": link,
                "description": strip_markup(description),
            })

        if len(results) >= MAX_FEED_ITEMS:
            break

    return results


# --------------------------------------------------
# LANGUAGE MAPPING
# --------------------------------------------------

def language_choice(code):

    value = (
        code or "unknown"
    ).lower()

    return {
        "en": Resource.Language.ENGLISH,
        "hi": Resource.Language.HINDI,
        "other": Resource.Language.OTHER,
        "unknown": Resource.Language.UNKNOWN,
    }.get(
        value,
        Resource.Language.UNKNOWN
    )


# --------------------------------------------------
# PLACEMENT RELEVANCE AND TOPIC CLASSIFICATION
# --------------------------------------------------

# RSS entries must match at least one topic group before import.
TOPIC_RULES = [
    ("Aptitude", "Quantitative Aptitude", (
        "quantitative aptitude", "logical reasoning", "verbal reasoning",
        "number series", "percentages", "profit and loss", "time and work",
        "time speed distance", "permutation", "combination", "probability",
        "placement aptitude", "aptitude test",
    )),
    ("Interview Preparation", "Interview Preparation", (
        "technical interview", "hr interview", "interview questions",
        "interview preparation", "job interview", "behavioral interview",
        "resume", "cv writing", "cover letter", "placement preparation",
        "campus placement", "job search", "career advice",
    )),
    ("Data Structures and Algorithms", "Data Structures and Algorithms", (
        "data structure", "algorithm", "leetcode", "coding interview",
        "competitive programming", "dynamic programming", "binary search",
        "linked list", "binary tree", "graph traversal", "sorting algorithm",
        "time complexity", "space complexity",
    )),
    ("Database Management", "DBMS and SQL", (
        "database", "sql", "postgresql", "mysql", "mongodb",
        "database management", "database query", "joins",
    )),
    ("Operating Systems", "Operating Systems", (
        "operating system", "process scheduling", "deadlock",
        "memory management", "virtual memory", "linux kernel",
        "concurrency", "thread synchronization",
    )),
    ("Web Development", "HTML CSS JavaScript", (
        "html", "css", "javascript", "typescript", "react",
        "frontend", "front-end", "web development", "web developer",
        "responsive design", "dom", "next.js", "node.js",
        "website performance", "web accessibility",
    )),
    ("Programming", "Programming Languages", (
        "python", "java programming", "c++", " c language",
        "programming language", "object-oriented programming",
        "oop", "debugging", "software development", "code tutorial",
        "programming tutorial",
    )),
    ("Artificial Intelligence", "AI and Machine Learning", (
        "artificial intelligence", "machine learning", "deep learning",
        "neural network", "large language model", "generative ai",
        "data science", "natural language processing",
    )),
    ("Cybersecurity", "Cybersecurity Fundamentals", (
        "cybersecurity", "cyber security", "network security",
        "ethical hacking", "penetration testing", "cryptography",
        "phishing", "web security", "vulnerability",
    )),
    ("Tools and DevOps", "Developer Tools and DevOps", (
        "git", "github", "docker", "kubernetes", "devops",
        "continuous integration", "ci/cd", "cloud computing",
        "linux command", "version control", "api development",
    )),
]


def classify_placement_resource(title, description=""):
    """Return a placement-relevant (subject, topic), or None."""
    text = f" {title or ''} {description or ''} ".casefold()
    for subject, topic, keywords in TOPIC_RULES:
        if any(keyword.casefold() in text for keyword in keywords):
            return subject, topic
    return None


# --------------------------------------------------
# TOPIC CREATION
# --------------------------------------------------

def get_topic(subject, topic_name):

    topic, _ = Topic.objects.get_or_create(
        subject=subject,
        name=topic_name,
        defaults={
            "difficulty": Difficulty.EASY
        },
    )

    return topic


# --------------------------------------------------
# DUPLICATE-SAFE RESOURCE IMPORT
# --------------------------------------------------

def import_one_resource(
    *,
    title,
    url,
    source_name,
    domain,
    subject,
    topic_name,
    language,
    resource_type,
    external_id=""
):

    if not title or not approved_https_url(
        url,
        domain
    ):

        return "rejected"

    # Check URL and external ID to prevent duplicates.
    duplicate_query = Q(url=url)

    if external_id:

        duplicate_query |= Q(
            external_id=external_id
        )

    if Resource.objects.filter(
        duplicate_query
    ).exists():

        return "duplicate"

    topic = get_topic(
        subject,
        topic_name
    )

    Resource.objects.create(
        topic=topic,
        title=title[:200],
        type=resource_type,
        url=url,
        source=source_name[:255],
        language=language_choice(language),
        external_id=external_id[:255],
        is_auto_imported=True,
        status=ContentStatus.PUBLISHED,
        created_by=None,
    )

    return "imported"


# --------------------------------------------------
# COUNT RESULT SAFELY
# --------------------------------------------------

def record_result(counts, result):
    """
    Convert the function result 'duplicate' into
    the counter key 'duplicates'.

    This fixes the previous KeyError.
    """

    if result == "duplicate":

        counts["duplicates"] += 1

    elif result == "imported":

        counts["imported"] += 1

    elif result == "rejected":

        counts["rejected"] += 1

    else:

        counts["rejected"] += 1


# --------------------------------------------------
# MAIN DJANGO COMMAND
# --------------------------------------------------

class Command(BaseCommand):

    help = (
        "Import approved RSS/Atom articles, "
        "curated pages and licensed PDF links."
    )

    def add_arguments(self, parser):

        parser.add_argument(
            "--feeds-only",
            action="store_true",
            help="Import RSS/Atom feeds only.",
        )

        parser.add_argument(
            "--catalogue-only",
            action="store_true",
            help=(
                "Import curated pages and "
                "explicitly licensed PDFs only."
            ),
        )

    def handle(self, *args, **options):

        if (
            options["feeds_only"]
            and options["catalogue_only"]
        ):

            self.stderr.write(
                self.style.ERROR(
                    "Choose either --feeds-only "
                    "or --catalogue-only, not both."
                )
            )

            return

        counts = {
            "imported": 0,
            "duplicates": 0,
            "rejected": 0,
            "failed": 0,
        }

        # ==========================================
        # 1. RSS / ATOM FEEDS
        # ==========================================

        if not options["catalogue_only"]:

            for source in RESOURCE_SOURCES:

                if not source.get("enabled"):
                    continue

                name = source.get(
                    "name",
                    "Unnamed source"
                )

                self.stdout.write(
                    f"\nChecking feed: {name}"
                )

                try:

                    feed_data = fetch_feed(
                        source["feed_url"],
                        source["domain"]
                    )

                    entries = parse_feed(
                        feed_data,
                        source["feed_url"]
                    )

                except (
                    HTTPError,
                    URLError,
                    TimeoutError,
                    OSError,
                    ET.ParseError,
                    ValueError,
                    KeyError,
                ) as exc:

                    counts["failed"] += 1

                    self.stderr.write(
                        self.style.ERROR(
                            f"Feed failed ({name}): {exc}"
                        )
                    )

                    continue

                except Exception as exc:

                    counts["failed"] += 1

                    self.stderr.write(
                        self.style.ERROR(
                            f"Unexpected feed error ({name}): {exc}"
                        )
                    )

                    continue

                self.stdout.write(
                    f"Found {len(entries)} feed entries."
                )

                for entry in entries:

                    try:

                        category = classify_placement_resource(
                            entry["title"],
                            entry.get("description", ""),
                        )

                        if category is None:
                            counts["rejected"] += 1
                            self.stdout.write(
                                self.style.WARNING(
                                    f"Skipped unrelated article: {entry['title']}"
                                )
                            )
                            continue

                        subject, topic_name = category

                        result = import_one_resource(
                            title=entry["title"],
                            url=entry["url"],
                            source_name=name,
                            domain=source["domain"],
                            subject=subject,
                            topic_name=topic_name,
                            language=source.get(
                                "language",
                                "unknown"
                            ),
                            resource_type=(
                                Resource.ResourceType.ARTICLE
                            ),
                        )

                        record_result(
                            counts,
                            result
                        )

                        if result == "imported":

                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"Imported: {entry['title']}"
                                )
                            )

                        elif result == "rejected":

                            self.stdout.write(
                                self.style.WARNING(
                                    f"Rejected: {entry['title']}"
                                )
                            )

                    except Exception as exc:

                        counts["failed"] += 1

                        self.stderr.write(
                            self.style.ERROR(
                                f"Could not import "
                                f"{entry.get('title', 'entry')}: {exc}"
                            )
                        )

        # ==========================================
        # 2. CURATED WEBSITE RESOURCES
        # ==========================================

        if not options["feeds_only"]:

            for item in CURATED_RESOURCES:

                if not item.get("enabled"):
                    continue

                try:

                    resource_type = (
                        Resource.ResourceType.LINK
                        if item.get("type") == "link"
                        else Resource.ResourceType.ARTICLE
                    )

                    result = import_one_resource(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        source_name=item.get(
                            "name",
                            "Approved website"
                        ),
                        domain=item.get("domain", ""),
                        subject=item.get(
                            "subject",
                            "General"
                        ),
                        topic_name=item.get(
                            "topic",
                            "General resources"
                        ),
                        language=item.get(
                            "language",
                            "unknown"
                        ),
                        resource_type=resource_type,
                    )

                    record_result(
                        counts,
                        result
                    )

                    if result == "imported":

                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Imported website: {item['title']}"
                            )
                        )

                except Exception as exc:

                    counts["failed"] += 1

                    self.stderr.write(
                        self.style.ERROR(
                            f"Website import failed: {exc}"
                        )
                    )

            # ======================================
            # 3. LICENSED PDF RESOURCES
            # ======================================

            for item in LICENSED_PDF_RESOURCES:

                if not item.get("enabled"):
                    continue

                # Require explicit licence information.
                if (
                    not item.get("license")
                    or not item.get("license_url")
                ):

                    counts["rejected"] += 1

                    self.stderr.write(
                        self.style.WARNING(
                            "Skipped PDF without licence evidence: "
                            f"{item.get('title', 'Untitled')}"
                        )
                    )

                    continue

                license_url = item.get(
                    "license_url",
                    ""
                )

                license_domain = (
                    urlparse(license_url).hostname or ""
                )

                if not approved_https_url(
                    license_url,
                    license_domain
                ):

                    counts["rejected"] += 1
                    continue

                pdf_url = item.get(
                    "url",
                    ""
                )

                if not urlparse(
                    pdf_url
                ).path.lower().endswith(".pdf"):

                    counts["rejected"] += 1

                    self.stderr.write(
                        self.style.WARNING(
                            f"Skipped non-PDF URL: {pdf_url}"
                        )
                    )

                    continue

                source_label = (
                    f"{item.get('name', 'Open resource')} "
                    f"| {item['license']}"
                )

                try:

                    result = import_one_resource(
                        title=item.get("title", ""),
                        url=pdf_url,
                        source_name=source_label,
                        domain=item.get("domain", ""),
                        subject=item.get(
                            "subject",
                            "General"
                        ),
                        topic_name=item.get(
                            "topic",
                            "Open PDFs"
                        ),
                        language=item.get(
                            "language",
                            "unknown"
                        ),
                        resource_type=(
                            Resource.ResourceType.NOTES
                        ),
                    )

                    record_result(
                        counts,
                        result
                    )

                    if result == "imported":

                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Imported PDF: {item['title']}"
                            )
                        )

                except Exception as exc:

                    counts["failed"] += 1

                    self.stderr.write(
                        self.style.ERROR(
                            f"PDF import failed: {exc}"
                        )
                    )

        # ==========================================
        # 4. FINAL SUMMARY
        # ==========================================

        self.stdout.write("\n" + "=" * 48)

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported: {counts['imported']}"
            )
        )

        self.stdout.write(
            self.style.WARNING(
                f"Duplicates: {counts['duplicates']}"
            )
        )

        self.stdout.write(
            self.style.WARNING(
                f"Rejected / not relevant: {counts['rejected']}"
            )
        )

        self.stdout.write(
            self.style.ERROR(
                f"Failed feeds/items: {counts['failed']}"
            )
        )

        self.stdout.write("=" * 48)
