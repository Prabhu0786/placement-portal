
import json
import os

from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from content.models import ContentStatus, Difficulty, Resource, Topic


YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


# Subjects and search queries
SEARCHES = [
    (
        "Data Structures and Algorithms",
        "Data Structures and Algorithms",
        "Data Structures Algorithms tutorial for beginners",
        "Data Structures Algorithms tutorial Hindi",
    ),
    (
        "Programming",
        "Java and C++ Programming",
        "Java C++ programming tutorial for beginners",
        "Java C++ programming tutorial Hindi",
    ),
    (
        "Database Management",
        "DBMS and SQL",
        "DBMS SQL complete tutorial",
        "DBMS SQL complete tutorial Hindi",
    ),
    (
        "Operating Systems",
        "Operating Systems",
        "Operating System concepts tutorial",
        "Operating System concepts tutorial Hindi",
    ),
    (
        "Aptitude",
        "Quantitative Aptitude",
        "Quantitative aptitude placement preparation",
        "Quantitative aptitude placement preparation Hindi",
    ),
    (
        "Interview Preparation",
        "Technical and HR Interviews",
        "Technical HR interview preparation for freshers",
        "Technical HR interview preparation Hindi",
    ),
]


def youtube_request(url, params):
    """Send a GET request to the YouTube Data API."""

    request_url = url + "?" + urlencode(params)

    with urlopen(request_url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def detect_language(video_details):
    """
    Classify language using YouTube metadata
    and explicit language clues in the title.

    Returns:
        en      English
        hi      Hindi
        other   Other language
        unknown Language not identified
    """

    snippet = video_details.get("snippet", {})
    title = (snippet.get("title") or "").lower()

    # Explicit language clues in titles take priority.
    language_keywords = {
        "hi": [
            "hindi",
            "in hindi",
            "हिंदी",
        ],
        "other": [
            "telugu",
            "in telugu",
            "తెలుగు",
            "tamil",
            "in tamil",
            "தமிழ்",
            "malayalam",
            "kannada",
            "ಕನ್ನಡ",
            "bengali",
            "বাংলা",
            "urdu",
            "اردو",
        ],
    }

    for language, keywords in language_keywords.items():
        if any(keyword in title for keyword in keywords):
            return language

    # Check YouTube language metadata.
    language_code = (
        snippet.get("defaultAudioLanguage")
        or snippet.get("defaultLanguage")
        or ""
    ).lower()

    if language_code.startswith("hi"):
        return "hi"

    if language_code.startswith("en"):
        return "en"

    if language_code:
        return "other"

    return "unknown"


class Command(BaseCommand):

    help = "Import and update Hindi and English YouTube learning resources."

    def add_arguments(self, parser):

        parser.add_argument(
            "--max-results",
            type=int,
            default=5,
            help="Maximum videos per search (1-10).",
        )

    def handle(self, *args, **options):

        # Read YouTube API key.
        api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()

        if not api_key:
            raise CommandError(
                "YOUTUBE_API_KEY is missing. Check your environment variables."
            )

        max_results = options["max_results"]

        if not 1 <= max_results <= 10:
            raise CommandError(
                "--max-results must be between 1 and 10."
            )

        imported = 0
        updated = 0
        skipped = 0
        errors = 0

        # Process each subject.
        for subject, topic_name, english_query, hindi_query in SEARCHES:

            topic, _ = Topic.objects.get_or_create(
                subject=subject,
                name=topic_name,
                defaults={
                    "difficulty": Difficulty.EASY,
                },
            )

            # Search in English and Hindi.
            for language, query in (
                ("en", english_query),
                ("hi", hindi_query),
            ):

                self.stdout.write(
                    f"\nSearching ({language}): {query}"
                )

                try:

                    search_data = youtube_request(
                        YOUTUBE_SEARCH_URL,
                        {
                            "part": "snippet",
                            "type": "video",
                            "q": query,
                            "maxResults": max_results,
                            "relevanceLanguage": language,
                            "regionCode": "IN",
                            "safeSearch": "moderate",
                            "key": api_key,
                        },
                    )

                except HTTPError as exc:

                    detail = exc.read().decode(
                        "utf-8",
                        errors="replace",
                    )

                    self.stderr.write(
                        self.style.ERROR(
                            f"YouTube search error {exc.code}: "
                            f"{detail[:500]}"
                        )
                    )

                    errors += 1
                    continue

                except (
                    URLError,
                    TimeoutError,
                    OSError,
                    json.JSONDecodeError,
                ) as exc:

                    self.stderr.write(
                        self.style.ERROR(
                            f"Search failed: {exc}"
                        )
                    )

                    errors += 1
                    continue

                items = search_data.get("items", [])

                video_ids = [
                    item.get("id", {}).get("videoId")
                    for item in items
                    if item.get("id", {}).get("videoId")
                ]

                if not video_ids:
                    continue

                # Retrieve video language metadata.
                try:

                    details_data = youtube_request(
                        YOUTUBE_VIDEOS_URL,
                        {
                            "part": "snippet",
                            "id": ",".join(video_ids),
                            "key": api_key,
                        },
                    )

                except (
                    HTTPError,
                    URLError,
                    TimeoutError,
                    OSError,
                    json.JSONDecodeError,
                ) as exc:

                    self.stderr.write(
                        self.style.ERROR(
                            f"Could not retrieve video details: {exc}"
                        )
                    )

                    errors += 1
                    continue

                details_by_id = {
                    video.get("id"): video
                    for video in details_data.get("items", [])
                }

                # Process each video.
                for item in items:

                    video_id = item.get("id", {}).get("videoId")
                    snippet = item.get("snippet", {})

                    title = (
                        snippet.get("title") or ""
                    ).strip()

                    channel = (
                        snippet.get("channelTitle") or ""
                    ).strip()

                    if not video_id or not title:
                        skipped += 1
                        continue

                    video_url = (
                        f"https://www.youtube.com/watch?v={video_id}"
                    )

                    details = details_by_id.get(video_id)

                    if not details:
                        skipped += 1
                        continue

                    # Detect actual language from available metadata.
                    actual_language = detect_language(details)

                    # Find existing resource using video ID or URL.
                    existing = Resource.objects.filter(
                        Q(external_id=video_id)
                        | Q(url=video_url)
                    ).first()

                    if existing:

                        # Update language only when it is identified.
                        if (
                            actual_language != "unknown"
                            and existing.language != actual_language
                        ):

                            existing.language = actual_language

                            existing.save(
                                update_fields=["language"]
                            )

                            updated += 1

                            self.stdout.write(
                                self.style.WARNING(
                                    f"Updated language: {existing.title} "
                                    f"-> {actual_language}"
                                )
                            )

                        else:
                            skipped += 1

                        continue

                    # Create new YouTube resource.
                    Resource.objects.create(
                        topic=topic,
                        title=title[:200],
                        type="video",
                        url=video_url,
                        source=(
                            f"YouTube - {channel}"
                            if channel
                            else "YouTube"
                        )[:255],
                        language=actual_language,
                        external_id=video_id,
                        is_auto_imported=True,
                        status=ContentStatus.PUBLISHED,
                        created_by=None,
                    )

                    imported += 1

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Imported: {title} "
                            f"[{actual_language}]"
                        )
                    )

        # Final summary.
        self.stdout.write("\n" + "=" * 45)

        self.stdout.write(
            self.style.SUCCESS(
                f"New videos imported: {imported}"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Existing videos updated: {updated}"
            )
        )

        self.stdout.write(
            self.style.WARNING(
                f"Skipped: {skipped}"
            )
        )

        self.stdout.write(
            self.style.ERROR(
                f"Errors: {errors}"
            )
        )

        self.stdout.write("=" * 45)
