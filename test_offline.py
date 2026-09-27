"""Offline plan still builds when GROQ_API_KEY is missing or rejected."""
import json
import os

os.environ["GROQ_API_KEY"] = ""

from extract import extract_syllabus, local_extract_syllabus
from planner import allocate_hours, generate_weekly_plan, local_weekly_plan

SAMPLE = """
Course: Data Structures & Algorithms
Semester: Fall 2026
Course Outcomes
Students will understand data structures.
Unit 1: Complexity Analysis
Weightage: 15% Assessment Date: 2026-09-10
(cid:127) Introduction to Algorithms
(cid:127) Asymptotic Analysis
Unit 2: Trees
Weightage: 25% Assessment Date: 2026-10-15
- Binary Trees
- Heap
Assessment Pattern
Assignments: 20%
"""


def main():
    data = json.loads(local_extract_syllabus(SAMPLE))
    assert len(data) == 2, data
    assert data[0]["subject"] == "Data Structures & Algorithms"
    assert data[0]["chapters"] == ["Introduction to Algorithms", "Asymptotic Analysis"]
    assert data[0]["weightage"] == "15%"
    assert data[0]["exam_date"] == "2026-09-10"
    assert "Assignments" not in json.dumps(data)

    same = json.loads(extract_syllabus(SAMPLE))
    assert same[0]["chapters"][0] == "Introduction to Algorithms"

    allocated = allocate_hours(data, daily_hours=2)
    plan = json.loads(local_weekly_plan(allocated, daily_hours=2))
    assert len(plan["timetable"]) == 7
    slot = plan["timetable"][0]["slots"][0]
    assert slot["chapters_to_cover"]
    assert slot["duration_minutes"] > 0

    via_api_path = json.loads(generate_weekly_plan(allocated, daily_hours=2))
    assert len(via_api_path["timetable"]) == 7
    assert "No AI token" in via_api_path["weekly_summary"]
    print("offline plan ok")


if __name__ == "__main__":
    main()
