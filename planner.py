import json
import os
from datetime import date, datetime, timedelta
from dotenv import load_dotenv

try:
    from groq import Groq
except ImportError:
    Groq = None

load_dotenv()
# Set by generate_weekly_plan: "ai" when Groq answered, "local" otherwise.
plan_source = "local"


def _groq_client():
    key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not key or Groq is None:
        return None
    try:
        return Groq(api_key=key)
    except Exception:
        return None

def load_syllabus(path="syllabus.json"):
    with open(path, "r") as f:
        return json.load(f)
    

def calculate_priority(subject, today=None):
    if today is None:
        today = date.today()

    exam_date_str = subject.get("exam_date")
    weightage_str = subject.get("weightage", "0%")

    # Parse the weightage
    try:
        weightage = float(weightage_str.replace("%", "").strip())
    except:
        weightage = 10.0

    # Days remaining until the exam
    if exam_date_str:
        exam_date = datetime.strptime(exam_date_str, "%Y-%m-%d").date()
        days_remaining = max((exam_date - today).days, 1)
    else:
        days_remaining = 30
    
    # Priority score (higher weightage + fewer days left to the exam =  higher priority)
    priority = (weightage / days_remaining) * 100
    return priority


def allocate_hours(subjects, daily_hours=4):
    scored = []
    for subject in subjects:
        score = calculate_priority(subject)
        scored.append({
            "subject" : subject["subject"],
            "chapters" : subject.get("chapters", []),
            "exam_date" : subject.get("exam_date", "Not specified"),
            "priority_score" : score
        })
    
    scored.sort(key=lambda x: x["priority_score"], reverse=True)

    total_score = sum(s["priority_score"] for s in scored) or 1

    # Allocate minutes proportionally
    total_daily_minutes = daily_hours * 60

    for subject in scored:
        proportion = subject["priority_score"] / total_score
        minutes = round(proportion * total_daily_minutes)
        subject["daily_minutes"] = max(minutes, 20)

    return scored


def local_weekly_plan(allocated_subjects, daily_hours=4, days_ahead=7):
    """Spread chapters across the week. Same JSON shape the AI prompt asked for."""
    today = date.today()
    items = []
    for subject in allocated_subjects:
        chapters = subject.get("chapters") or [subject["subject"]]
        exam = subject.get("exam_date")
        if exam in (None, "", "Not specified"):
            exam = None
        for chapter in chapters:
            items.append({
                "subject": subject["subject"],
                "chapter": chapter,
                "exam_date": exam,
            })
    if not items:
        items = [{"subject": "Study", "chapter": "Review your notes", "exam_date": None}]

    buckets = [[] for _ in range(days_ahead)]
    for index, item in enumerate(items):
        buckets[index % days_ahead].append(item)

    timetable = []
    budget = int(daily_hours * 60)
    for day_index, bucket in enumerate(buckets):
        revising = not bucket
        if revising:
            bucket = [items[day_index % len(items)]]
        each = max(15, budget // len(bucket))
        slots = []
        for item in bucket:
            slots.append({
                "subject": item["subject"],
                "duration_minutes": each,
                "chapters_to_cover": [item["chapter"]],
                "exam_date": item["exam_date"],
                "notes": "Revision" if revising or day_index >= 5 else "",
            })
        timetable.append({
            "day": day_index + 1,
            "date": (today + timedelta(days=day_index)).isoformat(),
            "slots": slots,
            "total_study_minutes": each * len(slots),
        })
    return json.dumps({
        "timetable": timetable,
        "weekly_summary": (
            f"Local {days_ahead}-day plan, {daily_hours}h per day. "
            "No AI token was used."
        ),
    })


def generate_weekly_plan(allocated_subjects, daily_hours=4, days_ahead=7):
    global plan_source
    today = date.today()
    client = _groq_client()
    if not client:
        plan_source = "local"
        return local_weekly_plan(allocated_subjects, daily_hours, days_ahead)

    subjects_summary = ""

    for subject in allocated_subjects:
        subjects_summary += f"""
                Subject : {subject['subject']}
                Chapters : {', '.join(subject['chapters'])}
                Exam Date : {subject['exam_date']}
                Priority Score: {subject['priority_score']}
                Daily study time : {subject['daily_minutes']} minutes
            """
        
    prompt = f"""
            You are a study planner AI.

            Today is {today.strftime('%A, %d %B %Y')}.
            The student has {daily_hours} hours to study per day.
            Create a {days_ahead}-day study timetable.

            Here are the subjects with their priority scores and daily time allocations:
            {subjects_summary}

            Rules:
            1. Higher priority subjects get more time each day.
            2. Sequence chapters logically — foundational topics before advanced ones.
            3. Include short 10-minute breaks between subjects.
            4. On days 6 and 7 (weekend), add a 30-minute revision slot for the highest priority subject.
            5. Return ONLY valid JSON — no explanation, no markdown.

            Return this exact format:
            {{
            "timetable": [
                {{
                "day": 1,
                "date": "YYYY-MM-DD",
                "slots": [
                    {{
                    "subject": "string",
                    "duration_minutes": number,
                    "chapters_to_cover": ["string"],
                    "exam_date": "YYYY-MM-DD",
                    "notes": "string"
                    }}
                ],
                "total_study_minutes": number
                }}
            ],
            "weekly_summary": "string"
            }}
            """

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        raw = response.choices[0].message.content
        json.loads(clean_json_response(raw))
        plan_source = "ai"
        return raw
    except Exception:
        plan_source = "local"
        return local_weekly_plan(allocated_subjects, daily_hours, days_ahead)

def clean_json_response(raw):
    start = raw.find("{")
    end = raw.rfind("}")

    if start == -1 or end == -1:
        raise ValueError("No JSON found")

    return raw[start:end + 1]


def display_timetable(timetable_data):
    print("\n" + "="*60)
    print("📚 YOUR STUDY TIMETABLE")
    print("="*60)

    for day in timetable_data["timetable"]:
        print(f"\n📅 Day {day['day']} — {day['date']}")
        print("-" * 40)
        for slot in day["slots"]:
            chapters = ", ".join(slot["chapters_to_cover"])
            print(f"  ⏱  {slot['duration_minutes']} min | {slot['subject']}")
            print(f"      Chapters: {chapters}")
            if slot.get("notes"):
                print(f"      Note: {slot['notes']}")
        print(f"  Total: {day['total_study_minutes']} minutes")

    print("\n" + "="*60)
    print("📝 WEEKLY SUMMARY")
    print(timetable_data.get("weekly_summary", ""))
    print("="*60 + "\n")

def main():
    print("Loading syllabus")
    subjects = load_syllabus()

    try:
        daily_hours = float(input("How many hours per day you can study? (default 4)"))
    except:
        daily_hours = 4.0

    print("Allocating study time across subjects")
    allocated = allocate_hours(subjects, daily_hours)

    print("Priority order")
    for i , subject in enumerate(allocated, 1):
        print(f" {i}. {subject['subject']} - Score: {subject['priority_score']} - {subject['daily_minutes']} min/day ")

    raw = generate_weekly_plan(allocated, daily_hours)
    cleaned = clean_json_response(raw)

    timetable_data = json.loads(cleaned)
    display_timetable(timetable_data)
    
    with open("timetable.json", "w") as f:
        json.dump(timetable_data, f, indent=2)
    
    print("saved to timetable json")


if __name__ == "__main__":
    main()



