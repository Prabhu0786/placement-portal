from django.core.management.base import BaseCommand

from content.models import ContentStatus, Question, Topic

TOPICS = [
    ("Interview", "HR and Project Questions", "easy"),
    ("Interview", "Behavioural Questions", "easy"),
    ("Interview", "Technical Interview", "medium"),
]

# (topic name, difficulty, question, model answer, tips)
QUESTIONS = [
    # ---- HR
    ("HR and Project Questions", "easy", "Tell me about yourself.",
     "Keep it to one or two minutes: present (your course and current focus), past (relevant projects or internships), and future (the role you want and why it fits).",
     "Do not read your resume aloud. Finish by linking yourself to this role."),
    ("HR and Project Questions", "medium", "Why should we hire you?",
     "Match two or three of your strongest skills to the job requirements, back each with a short example, and show that you are keen to learn.",
     "Be specific and honest. Avoid claims such as 'I am hard-working' without evidence."),
    ("HR and Project Questions", "medium", "Describe a project you worked on and explain your individual contribution.",
     "State the problem and goal, your team size and the technologies used. Then clearly separate what YOU built or decided from what the team did. End with the result and what you learned.",
     "Interviewers look for ownership and honesty. Be ready to explain any line of code you mention."),
    ("HR and Project Questions", "easy", "What are your strengths and weaknesses?",
     "Name two real strengths and give one example for each. For a weakness, choose a genuine one that does not block the job, and explain the steps you are taking to improve it.",
     "Avoid clichés such as 'I am a perfectionist'. A weakness you are actively fixing shows maturity."),
    ("HR and Project Questions", "medium", "Where do you see yourself in five years?",
     "Describe realistic growth in skills and responsibility in the field you are applying for, for example becoming a confident developer who can lead a small module. Show that you want to grow with the company.",
     "Do not say you plan to leave, and do not be vague. Tie your goals to the role."),
    ("HR and Project Questions", "easy", "Why do you want to work for our company?",
     "Show you have researched the company: its products, its values or recent work. Explain how the role fits your skills and what you hope to learn.",
     "Generic answers such as 'it is a big company' stand out as weak. Mention something specific."),
    # ---- Behavioural
    ("Behavioural Questions", "medium", "Tell me about a time you worked in a team and faced a disagreement. How did you handle it?",
     "Use STAR. Situation: the team project and the disagreement. Task: what you needed to achieve. Action: how you listened, discussed options calmly and agreed on a way forward. Result: the outcome and what you learned about teamwork.",
     "Never blame teammates. Show that you listen and look for a solution that helps the team."),
    ("Behavioural Questions", "medium", "Describe a time you failed or made a mistake. What did you learn?",
     "Pick a real, modest mistake. Explain the situation, what went wrong, what you did to fix it, and the specific habit you changed afterwards.",
     "Take responsibility. A good answer ends with something you now do differently."),
    ("Behavioural Questions", "medium", "Tell me about a time you had to learn something new quickly.",
     "Describe what you needed to learn and why, how you went about it (documentation, practice, asking for help), how quickly you became useful, and what you would do again.",
     "Show a clear learning method, not just 'I worked hard'."),
    ("Behavioural Questions", "hard", "Describe a situation where you had a tight deadline. How did you manage it?",
     "Explain the deadline and what was at stake. Describe how you prioritised the most important work, planned your time, communicated early about risks, and what you delivered.",
     "Mention how you communicated, not just how hard you worked."),
    # ---- Technical
    ("Technical Interview", "medium", "Explain the difference between a process and a thread.",
     "A process is an independent program in execution with its own memory space. A thread is a lightweight unit of execution inside a process, and threads of the same process share its memory and resources. Threads are cheaper to create and switch between, but sharing memory means they need careful synchronisation. Processes are isolated, so one crashing does not corrupt another.",
     "Give a quick example, such as a browser using separate processes for tabs and threads for tasks inside a tab."),
    ("Technical Interview", "medium", "What is normalization in a database, and why is it used?",
     "Normalization organises data into related tables to reduce redundancy and avoid update, insert and delete anomalies. It follows normal forms such as 1NF, 2NF and 3NF. The trade-off is that queries may need more joins.",
     "Be ready to give a small example, such as splitting customer details from orders."),
    ("Technical Interview", "easy", "Explain the four pillars of object-oriented programming.",
     "Encapsulation bundles data with the methods that use it and hides internal details. Abstraction exposes only what is necessary. Inheritance lets a class reuse and extend another class. Polymorphism lets different classes be used through the same interface, each behaving in its own way.",
     "Give one short example for each, for example Animal with Dog and Cat for polymorphism."),
    ("Technical Interview", "medium", "What happens when you type a URL into a browser and press Enter?",
     "The browser looks up the server's IP address using DNS, opens a TCP connection (with TLS for HTTPS), sends an HTTP request, the server processes it and returns a response, and the browser renders the HTML, then loads CSS, JavaScript and images with further requests.",
     "Mention each step briefly in order. Add caching or load balancers if you know them."),
    ("Technical Interview", "easy", "What is the difference between a primary key and a foreign key?",
     "A primary key uniquely identifies each row in a table and cannot be null or repeated. A foreign key is a column that refers to the primary key of another table, linking the rows and enforcing referential integrity.",
     "A small example helps: the customer id is the primary key in Customers and a foreign key in Orders."),
    ("Technical Interview", "easy", "What is the difference between a stack and a queue?",
     "A stack is last in, first out (LIFO), so the most recently added item is removed first, like a pile of plates. A queue is first in, first out (FIFO), so items leave in the order they arrived, like people in a line. Stacks suit undo and function calls, and queues suit scheduling and breadth-first search.",
     "Always connect the data structure to a real use."),
]


class Command(BaseCommand):
    help = "Load sample interview questions (HR, behavioural and technical). Safe to run more than once."

    def add_arguments(self, parser):
        parser.add_argument("--draft", action="store_true", help="Load as Drafts instead of Published.")

    def handle(self, *args, **options):
        status = ContentStatus.DRAFT if options["draft"] else ContentStatus.PUBLISHED
        topics = {}
        for subject, name, difficulty in TOPICS:
            topics[name], _ = Topic.objects.get_or_create(subject=subject, name=name, defaults={"difficulty": difficulty})
        created = 0
        for topic_name, difficulty, text, answer, tips in QUESTIONS:
            _, was_created = Question.objects.get_or_create(
                topic=topics[topic_name], text=text,
                defaults={"type": "interview", "difficulty": difficulty, "options": [], "answer": answer,
                          "explanation": tips, "status": status},
            )
            created += was_created
        self.stdout.write(self.style.SUCCESS(
            f"Done. {created} new interview question(s) added as {status}; {len(QUESTIONS) - created} already existed."))
