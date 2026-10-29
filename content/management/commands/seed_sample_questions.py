from django.core.management.base import BaseCommand

from content.models import ContentStatus, Question, Topic

# (subject, topic name, topic difficulty)
TOPICS = [
    ("Aptitude", "Percentages", "easy"),
    ("Aptitude", "Profit and Loss", "easy"),
    ("Aptitude", "Time and Work", "medium"),
    ("Verbal", "Grammar", "easy"),
    ("Verbal", "Vocabulary", "easy"),
    ("Data Structures", "Arrays", "medium"),
    ("Data Structures", "Stacks and Queues", "medium"),
    ("DBMS", "SQL Basics", "easy"),
    ("Python", "Basics", "easy"),
    ("Interview", "HR and Project Questions", "easy"),
]

# Multiple choice: options is a list and answer must be one of them.
# Open question: options is [] and answer holds the model answer.
QUESTIONS = [
    # ---- Aptitude / Percentages
    dict(topic="Percentages", type="aptitude", difficulty="easy",
         text="What is 15% of 240?",
         options=["24", "30", "36", "40"], answer="36",
         explanation="15% of 240 = 240 x 15 / 100 = 36."),
    dict(topic="Percentages", type="aptitude", difficulty="easy",
         text="A price rises from 200 to 250. What is the percentage increase?",
         options=["20%", "25%", "30%", "50%"], answer="25%",
         explanation="Increase = 50. Percentage increase = 50 / 200 x 100 = 25%."),
    dict(topic="Percentages", type="aptitude", difficulty="medium",
         text="If 40% of a number is 80, what is the number?",
         options=["120", "160", "200", "320"], answer="200",
         explanation="Number = 80 / 0.40 = 200."),
    # ---- Aptitude / Profit and Loss
    dict(topic="Profit and Loss", type="aptitude", difficulty="easy",
         text="An article bought for Rs 500 is sold for Rs 600. What is the profit percentage?",
         options=["10%", "15%", "20%", "25%"], answer="20%",
         explanation="Profit = 100. Profit % = 100 / 500 x 100 = 20%. Profit is always taken on the cost price."),
    dict(topic="Profit and Loss", type="aptitude", difficulty="medium",
         text="An item is sold for Rs 720 at a 20% loss. What was its cost price?",
         options=["Rs 864", "Rs 900", "Rs 936", "Rs 1000"], answer="Rs 900",
         explanation="At a 20% loss, selling price = 80% of cost price. Cost price = 720 / 0.80 = Rs 900."),
    # ---- Aptitude / Time and Work
    dict(topic="Time and Work", type="aptitude", difficulty="medium",
         text="A can finish a job in 10 days and B can finish it in 15 days. Working together, how many days will they take?",
         options=["5 days", "6 days", "8 days", "12.5 days"], answer="6 days",
         explanation="Work per day = 1/10 + 1/15 = 5/30 = 1/6. So they need 6 days."),
    dict(topic="Time and Work", type="aptitude", difficulty="medium",
         text="12 workers complete a job in 15 days. If all workers work at the same rate, how many days will 9 workers need?",
         options=["11.25 days", "18 days", "20 days", "25 days"], answer="20 days",
         explanation="Total work = 12 x 15 = 180 worker-days. With 9 workers: 180 / 9 = 20 days."),
    # ---- Verbal / Grammar
    dict(topic="Grammar", type="verbal", difficulty="easy",
         text="Choose the grammatically correct sentence.",
         options=["She don't like coffee.", "She doesn't like coffee.", "She not like coffee.", "She no likes coffee."],
         answer="She doesn't like coffee.",
         explanation="With a third-person singular subject (she), the negative present tense uses 'doesn't'."),
    dict(topic="Grammar", type="verbal", difficulty="medium",
         text="Fill in the blank: Neither of the two answers ___ correct.",
         options=["is", "are", "were", "be"], answer="is",
         explanation="'Neither' refers to each one separately, so it takes a singular verb: 'is'."),
    # ---- Verbal / Vocabulary
    dict(topic="Vocabulary", type="verbal", difficulty="easy",
         text="Choose the word closest in meaning to 'abundant'.",
         options=["Scarce", "Plentiful", "Tiny", "Costly"], answer="Plentiful",
         explanation="'Abundant' means existing in large quantities, which is 'plentiful'."),
    dict(topic="Vocabulary", type="verbal", difficulty="easy",
         text="Choose the word opposite in meaning to 'expand'.",
         options=["Contract", "Grow", "Extend", "Stretch"], answer="Contract",
         explanation="To expand is to become larger; to contract is to become smaller."),
    # ---- Data Structures / Arrays
    dict(topic="Arrays", type="technical", difficulty="easy",
         text="What is the time complexity of accessing an array element by its index?",
         options=["O(1)", "O(n)", "O(log n)", "O(n^2)"], answer="O(1)",
         explanation="Arrays are stored in contiguous memory, so the address of any element is computed directly from its index."),
    dict(topic="Arrays", type="technical", difficulty="medium",
         text="What is the worst-case time complexity of binary search on a sorted array of n elements?",
         options=["O(1)", "O(log n)", "O(n)", "O(n log n)"], answer="O(log n)",
         explanation="Each step halves the search range, so at most about log2(n) steps are needed."),
    dict(topic="Arrays", type="coding", difficulty="easy",
         text="Write a function that reverses an array in place without using extra space.",
         options=[],
         answer=("def reverse(arr):\n"
                 "    left, right = 0, len(arr) - 1\n"
                 "    while left < right:\n"
                 "        arr[left], arr[right] = arr[right], arr[left]\n"
                 "        left += 1\n"
                 "        right -= 1\n"
                 "    return arr"),
         explanation="Two-pointer technique: swap the first and last elements and move inwards. Time O(n), extra space O(1)."),
    dict(topic="Arrays", type="coding", difficulty="medium",
         text="Write a function that returns the second largest distinct element of an array, or None if there is none.",
         options=[],
         answer=("def second_largest(arr):\n"
                 "    largest = second = None\n"
                 "    for x in arr:\n"
                 "        if largest is None or x > largest:\n"
                 "            second = largest\n"
                 "            largest = x\n"
                 "        elif x != largest and (second is None or x > second):\n"
                 "            second = x\n"
                 "    return second"),
         explanation="Single pass tracking the two largest distinct values. Time O(n), space O(1). Check duplicates such as [5, 5, 5] and short arrays."),
    # ---- Data Structures / Stacks and Queues
    dict(topic="Stacks and Queues", type="technical", difficulty="easy",
         text="Which data structure follows the Last In, First Out (LIFO) principle?",
         options=["Queue", "Stack", "Linked list", "Binary tree"], answer="Stack",
         explanation="In a stack, the most recently added element is the first one removed."),
    dict(topic="Stacks and Queues", type="technical", difficulty="medium",
         text="Which data structure is normally used to implement breadth-first search (BFS) on a graph?",
         options=["Stack", "Queue", "Heap", "Hash table"], answer="Queue",
         explanation="BFS visits nodes level by level, so nodes must be processed in the order they were discovered: first in, first out."),
    # ---- DBMS / SQL
    dict(topic="SQL Basics", type="technical", difficulty="easy",
         text="Which SQL clause is used to filter groups after a GROUP BY?",
         options=["WHERE", "HAVING", "ORDER BY", "LIMIT"], answer="HAVING",
         explanation="WHERE filters individual rows before grouping. HAVING filters the groups produced by GROUP BY."),
    dict(topic="SQL Basics", type="technical", difficulty="easy",
         text="Which keyword removes duplicate rows from a SELECT result?",
         options=["UNIQUE", "DISTINCT", "DIFFERENT", "REMOVE"], answer="DISTINCT",
         explanation="SELECT DISTINCT returns only unique rows."),
    dict(topic="SQL Basics", type="technical", difficulty="medium",
         text="Explain the difference between INNER JOIN and LEFT JOIN.",
         options=[],
         answer=("INNER JOIN returns only the rows that have a match in both tables. "
                 "LEFT JOIN returns all rows from the left table, and the matching rows from the right table; "
                 "where there is no match, the right-side columns are NULL."),
         explanation="Give a small example, such as customers and orders: LEFT JOIN also lists customers who have no orders."),
    # ---- Python
    dict(topic="Basics", type="technical", difficulty="easy",
         text="What does print(type([])) display in Python?",
         options=["<class 'list'>", "<class 'tuple'>", "<class 'dict'>", "list"], answer="<class 'list'>",
         explanation="[] is an empty list literal, so its type is the list class."),
    dict(topic="Basics", type="technical", difficulty="easy",
         text='What does len("placement") return?',
         options=["7", "8", "9", "10"], answer="9",
         explanation="p-l-a-c-e-m-e-n-t has 9 characters."),
    dict(topic="Basics", type="technical", difficulty="medium",
         text="Which of these Python types is immutable?",
         options=["list", "dict", "set", "tuple"], answer="tuple",
         explanation="Tuples cannot be changed after creation. Lists, dictionaries and sets can be modified."),
    # ---- Interview
    dict(topic="HR and Project Questions", type="interview", difficulty="easy",
         text="Tell me about yourself.",
         options=[],
         answer=("Keep it to about one to two minutes: present (course and current focus), past (relevant projects or "
                 "internships), and future (the role you want and why it fits)."),
         explanation="Avoid reading your resume aloud. Finish with why you are interested in this role."),
    dict(topic="HR and Project Questions", type="interview", difficulty="medium",
         text="Why should we hire you?",
         options=[],
         answer=("Match two or three of your strongest skills to the job requirements, back each with a short example, "
                 "and show enthusiasm to learn."),
         explanation="Be specific and honest. Avoid general claims such as 'I am hard-working' without evidence."),
    dict(topic="HR and Project Questions", type="interview", difficulty="medium",
         text="Describe a project you worked on and explain your individual contribution.",
         options=[],
         answer=("State the problem and goal, your team size, the technologies used, then clearly separate what YOU built or "
                 "decided from what the team did. End with the result and what you learned."),
         explanation="Interviewers look for ownership and honesty. Be ready to explain any line of code you mention."),
]


class Command(BaseCommand):
    help = "Load sample topics and practice questions (safe to run more than once)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--draft",
            action="store_true",
            help="Load the questions as Drafts instead of Published (to practise the approval workflow).",
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
        for item in QUESTIONS:
            _, was_created = Question.objects.get_or_create(
                topic=topics[item["topic"]],
                text=item["text"],
                defaults={
                    "type": item["type"],
                    "difficulty": item["difficulty"],
                    "options": item["options"],
                    "answer": item["answer"],
                    "explanation": item["explanation"],
                    "status": status,
                },
            )
            created += was_created
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {created} new question(s) added as {status}; "
                f"{len(QUESTIONS) - created} already existed."
            )
        )
