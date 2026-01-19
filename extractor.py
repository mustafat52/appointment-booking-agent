# extractor.py

import json
import os
import google.generativeai as genai

GENAI_API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "models/gemini-flash-latest")

genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel(MODEL_NAME)


SYSTEM_PROMPT = """
You are an information extraction engine for a doctor appointment system.

Your job:
- Extract structured information from a single user message.
- Do NOT make decisions.
- Do NOT guess missing data.
- Do NOT normalize dates or times.
- If unsure, return null.

Return ONLY valid JSON in the exact schema below.
No explanations. No markdown.

Schema:
{
  "intent": "BOOK | CANCEL | RESCHEDULE | null",
  "date_text": "string | null",
  "time_text": "string | null",
  "patient_name": "string | null",
  "patient_phone": "string | null",
  "confidence": "high | medium | low"
}
"""


def extract_entities(user_message: str, current_intent: str | None = None) -> dict:
    """
    Phase-5 extractor.
    Stateless. Safe. JSON-only.
    """

    prompt = f"""
{SYSTEM_PROMPT}

User message:
"{user_message}"

Current intent (if known):
"{current_intent}"
"""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()

        data = json.loads(text)

        # ---- HARD SAFETY GUARDS ----
        if not isinstance(data, dict):
            raise ValueError("Invalid JSON")

        for key in [
            "intent",
            "date_text",
            "time_text",
            "patient_name",
            "patient_phone",
            "confidence",
        ]:
            if key not in data:
                data[key] = None

        if data["confidence"] not in {"high", "medium", "low"}:
            data["confidence"] = "low"

        return data

    except Exception:
        # Absolute fallback: extractor must NEVER break the system
        return {
            "intent": None,
            "date_text": None,
            "time_text": None,
            "patient_name": None,
            "patient_phone": None,
            "confidence": "low",
        }
