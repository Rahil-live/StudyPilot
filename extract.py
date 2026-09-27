import pdfplumber
import os
import re
import json
from dotenv import load_dotenv

try:
    from groq import Groq
except ImportError:
    Groq = None

load_dotenv()
# Set by extract_syllabus: "ai" when Groq answered, "local" when it did not.
syllabus_source = "local"


def extact_text_from_pdf(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text


def _groq_client():
    key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not key or Groq is None:
        return None
    try:
        return Groq(api_key=key)
    except Exception:
        return None


def local_extract_syllabus(text):
    """Turn syllabus text into the same JSON list the AI used to return."""
    subject = None
    units = []
    current = None

    def is_noise(line):
        low = line.lower()
        return low.startswith((
            "semester", "credits", "course outcomes", "students will",
            "assignments:", "mid semester", "end semester",
        ))

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        course = re.match(r"^course\s*:\s*(.+)$", line, re.I)
        if course and not subject:
            subject = course.group(1).strip()
            continue
        if re.match(r"^(assessment pattern|references|recommended books|textbooks)\b", line, re.I):
            if current:
                units.append(current)
                current = None
            continue
        if re.match(r"^(unit|module)\b", line, re.I):
            if current:
                units.append(current)
            current = {
                "subject": "",
                "unit": line,
                "chapters": [],
                "exam_date": None,
                "weightage": None,
            }
            continue
        if current is None:
            continue
        weight = re.search(r"weightage\s*:\s*(\d+)\s*%", line, re.I)
        exam = re.search(r"(?:assessment|exam)\s*date\s*:\s*(\d{4}-\d{2}-\d{2})", line, re.I)
        if weight or exam:
            if weight:
                current["weightage"] = weight.group(1) + "%"
            if exam:
                current["exam_date"] = exam.group(1)
            continue
        if is_noise(line):
            continue
        chapter = re.sub(r"^\(cid:\d+\)\s*", "", line)
        chapter = re.sub(r"^[-*•·]\s*", "", chapter).strip()
        if chapter:
            current["chapters"].append(chapter)

    if current:
        units.append(current)

    subject = subject or "Syllabus"
    if not units:
        chapters = [ln.strip() for ln in text.splitlines() if len(ln.strip()) > 3][:40]
        units = [{
            "subject": subject,
            "unit": "Topics",
            "chapters": chapters or ["Review your syllabus"],
            "exam_date": None,
            "weightage": None,
        }]
    for unit in units:
        unit["subject"] = subject
        if not unit["chapters"]:
            unit["chapters"] = [unit["unit"]]
    return json.dumps(units)


def extract_syllabus(text):
    global syllabus_source
    client = _groq_client()
    if client:
        prompt = f"""
            You are a structured data explorer.
            Extract Only syllabus unit.
            Each unit should become one JSON object.

            Do NOT create a separate object for the list of all units.
            Do NOT treat unit names as chapters.
            The chapters field should contain only the topics listed under that unit.

            Return ONLY valid JSON.

            Schema:

            [
            {{
                "subject": "string",
                "unit": "string",
                "chapters": ["string"],
                "exam_date": "YYYY-MM-DD or null",
                "weightage": "percentage or null"
            }}
            ]

            Syllabus text:

            {text}
        """
        try:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            raw = response.choices[0].message.content
            json.loads(clean_json_response(raw))
            syllabus_source = "ai"
            return raw
        except Exception:
            pass
    syllabus_source = "local"
    return local_extract_syllabus(text)


def clean_json_response(raw):
    start = raw.find("[")
    end = raw.rfind("]")

    if start == -1 or end == -1:
        raise ValueError("No JSON found")

    return raw[start : end + 1]


def main():
    text = extact_text_from_pdf("Information_Economics_Syllabus.pdf")
    ## send this text to the AI model
    raw_output = extract_syllabus(text)
    cleaned = clean_json_response(raw_output)
    data = json.loads(cleaned)
    with open("syllabus.json", "w") as f:
        json.dump(data, f, indent=2)
    
    print("Json has been written properly")

if __name__ == "__main__":
    main()
