from django.core.management.base import BaseCommand

from content.management.commands.seed_sample_questions import TOPICS
from content.models import ContentStatus, Resource, Topic

# (topic name, title, type, url, source)
RESOURCES = [
    # ---- Aptitude
    ("Percentages", "Percentage: concept and basic formulas", "article",
     "https://en.wikipedia.org/wiki/Percentage", "Wikipedia"),
    ("Percentages", "IndiaBIX: Percentage practice questions", "link",
     "https://www.indiabix.com/aptitude/percentage/", "IndiaBIX"),
    ("Profit and Loss", "IndiaBIX: Profit and Loss practice questions", "link",
     "https://www.indiabix.com/aptitude/profit-and-loss/", "IndiaBIX"),
    ("Time and Work", "IndiaBIX: Time and Work practice questions", "link",
     "https://www.indiabix.com/aptitude/time-and-work/", "IndiaBIX"),
    # ---- Verbal
    ("Grammar", "English grammar overview", "article",
     "https://en.wikipedia.org/wiki/English_grammar", "Wikipedia"),
    ("Grammar", "LearnEnglish: Grammar lessons and exercises", "link",
     "https://learnenglish.britishcouncil.org/grammar", "British Council"),
    ("Vocabulary", "Merriam-Webster: Word of the Day", "link",
     "https://www.merriam-webster.com/word-of-the-day", "Merriam-Webster"),
    # ---- Data structures
    ("Arrays", "Array data structure", "article",
     "https://en.wikipedia.org/wiki/Array_(data_structure)", "Wikipedia"),
    ("Arrays", "Binary search algorithm", "article",
     "https://en.wikipedia.org/wiki/Binary_search_algorithm", "Wikipedia"),
    ("Arrays", "Big O notation (time complexity)", "article",
     "https://en.wikipedia.org/wiki/Big_O_notation", "Wikipedia"),
    ("Arrays", "MIT OpenCourseWare: Introduction to Algorithms (6.006)", "video",
     "https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/", "MIT OpenCourseWare"),
    ("Stacks and Queues", "Stack (abstract data type)", "article",
     "https://en.wikipedia.org/wiki/Stack_(abstract_data_type)", "Wikipedia"),
    ("Stacks and Queues", "Queue (abstract data type)", "article",
     "https://en.wikipedia.org/wiki/Queue_(abstract_data_type)", "Wikipedia"),
    ("Stacks and Queues", "Breadth-first search", "article",
     "https://en.wikipedia.org/wiki/Breadth-first_search", "Wikipedia"),
    # ---- DBMS
    ("SQL Basics", "W3Schools: SQL tutorial", "link",
     "https://www.w3schools.com/sql/", "W3Schools"),
    ("SQL Basics", "W3Schools: SQL joins", "link",
     "https://www.w3schools.com/sql/sql_join.asp", "W3Schools"),
    ("SQL Basics", "SQLite Tutorial", "link",
     "https://www.sqlitetutorial.net/", "SQLite Tutorial"),
    # ---- Python
    ("Basics", "The Python Tutorial (official documentation)", "article",
     "https://docs.python.org/3/tutorial/", "python.org"),
    ("Basics", "Python: getting started", "link",
     "https://www.python.org/about/gettingstarted/", "python.org"),
    ("Basics", "Harvard CS50x: Introduction to Computer Science", "video",
     "https://cs50.harvard.edu/x/", "Harvard CS50"),
    # ---- Interview
    ("HR and Project Questions", "Job interview: overview and common formats", "article",
     "https://en.wikipedia.org/wiki/Job_interview", "Wikipedia"),
    ("HR and Project Questions", "Resume (curriculum vitae): what it contains", "article",
     "https://en.wikipedia.org/wiki/R%C3%A9sum%C3%A9", "Wikipedia"),
]


class Command(BaseCommand):
    help = "Load sample study resources (links to free learning material). Safe to run more than once."

    def add_arguments(self, parser):
        parser.add_argument(
            "--draft",
            action="store_true",
            help="Load as Drafts instead of Published (to practise the approval workflow).",
        )

    def handle(self, *args, **options):
        status = ContentStatus.DRAFT if options["draft"] else ContentStatus.PUBLISHED
        topics = {}
        for subject, name, difficulty in TOPICS:
            topic, _ = Topic.objects.get_or_create(
                subject=subject, name=name, defaults={"difficulty": difficulty}
            )
            topics[name] = topic

        created = 0
        for topic_name, title, rtype, url, source in RESOURCES:
            _, was_created = Resource.objects.get_or_create(
                topic=topics[topic_name],
                title=title,
                defaults={"type": rtype, "url": url, "source": source, "status": status},
            )
            created += was_created
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {created} new resource(s) added as {status}; "
                f"{len(RESOURCES) - created} already existed."
            )
        )
