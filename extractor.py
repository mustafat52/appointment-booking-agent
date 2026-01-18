# extractor.py

import os
import json
import google.generativeai as genai

GENAI_API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "models/gemini-flash-latest")

genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel(MODEL_NAME)


SYSTEM_PROMPT = """
You are an information extraction engine for a doctor appointment assistant.

Rules:
- Output STRICT JSON only
- Do NOT guess missing values
- Do NOT normalize date or time
- Extract exactly what the user said
- If unclear or missing, return null

Fields:
intent: BOOK | CANCEL | RESCHEDULE | null
date_text: string | null
time_text: string | null
patient_name: string | null
patient_phone: string | null
"""


def extract_entities(user_message: str) -> dict:
    print("🔍 [Extractor] User message:", user_message)

    prompt = f"""
{SYSTEM_PROMPT}

User message:
\"\"\"{user_message}\"\"\"
"""

    try:
        response = model.generate_content(prompt)
        raw_text = response.text.strip()
        print("🧠 [Extractor] Raw LLM output:", raw_text)

        data = json.loads(raw_text)

    except Exception as e:
        print("❌ [Extractor] Extraction failed:", str(e))
        return {
            "intent": None,
            "date_text": None,
            "time_text": None,
            "patient_name": None,
            "patient_phone": None,
        }

    extracted = {
        "intent": data.get("intent"),
        "date_text": data.get("date_text"),
        "time_text": data.get("time_text"),
        "patient_name": data.get("patient_name"),
        "patient_phone": data.get("patient_phone"),
    }

    print("✅ [Extractor] Parsed entities:", extracted)
    return extracted
