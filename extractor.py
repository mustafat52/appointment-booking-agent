# extractor.py

import json
import os
import google.generativeai as genai

GENAI_API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "models/gemini-flash-latest")

genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel(MODEL_NAME)


SYSTEM_PROMPT = """You are an information extraction engine for a doctor appointment assistant.

Your job is to extract structured information from a single user message.

IMPORTANT RULES:
- Output STRICT JSON only
- Do NOT explain anything
- Do NOT guess missing values
- If something is unclear, set it to null
- If confidence is low, say so explicitly

You do NOT manage conversation.
You do NOT decide what to ask next.
You ONLY extract what is clearly stated.

--------------------------------

FIELDS TO EXTRACT:

intent:
- One of: BOOK, CANCEL, RESCHEDULE
- null if intent is unclear

date_text:
- Raw date phrase exactly as the user said it
- Examples: "next friday", "3rd feb", "same day"
- null if not mentioned

time_text:
- Raw time phrase exactly as the user said it
- Examples: "3pm", "after lunch", "same time"
- null if not mentioned

patient_name:
- Extract ONLY if the user clearly states their name
- Examples: "My name is Rahul", "This is Mustafa"
- DO NOT infer from casual sentences
- null if not explicit

patient_phone:
- Extract ONLY if a phone number is explicitly given
- Digits only
- null otherwise

confidence:
- "high" → intent + info clearly stated
- "medium" → intent clear but some ambiguity
- "low" → unclear, vague, or conversational message

--------------------------------

EXAMPLES:

User: "Book an appointment next friday at 3pm"
Output:
{
  "intent": "BOOK",
  "date_text": "next friday",
  "time_text": "3pm",
  "patient_name": null,
  "patient_phone": null,
  "confidence": "high"
}

User: "Same time tomorrow"
Output:
{
  "intent": null,
  "date_text": "tomorrow",
  "time_text": "same time",
  "patient_name": null,
  "patient_phone": null,
  "confidence": "medium"
}

User: "Hi"
Output:
{
  "intent": null,
  "date_text": null,
  "time_text": null,
  "patient_name": null,
  "patient_phone": null,
  "confidence": "low"
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
