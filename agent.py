import os
import json
import re
from datetime import date

import google.generativeai as genai

from state import BookingState
from tools import check_availability, book_appointment


# ===============================
# Gemini Config (ENV ONLY)
# ===============================
GENAI_API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "models/gemini-flash-latest")

if not GENAI_API_KEY:
    raise RuntimeError("GOOGLE_GEMINI_API_KEY is not set")

genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel(MODEL_NAME)

TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def is_valid_time(value: str | None) -> bool:
    return bool(value and TIME_PATTERN.match(value))


def extract_with_gemini(user_message: str):
    today = date.today().isoformat()

    prompt = f"""
You are an information extraction system.

TODAY'S DATE IS: {today}

Return ONLY valid JSON.

Schema:
{{"intent": "BOOK or UNKNOWN",
  "date": "YYYY-MM-DD or null",
  "time": "HH:MM or null"
}}

Rules:
- Convert 3pm → 15:00
- If time is unclear, return null
- Do NOT guess time

Message:
{user_message}
"""

    response = model.generate_content(prompt)

    try:
        text = response.text.strip()
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception:
        return {"intent": "UNKNOWN", "date": None, "time": None}


def run_agent(user_message: str, state: BookingState) -> str:
    message_lower = user_message.lower().strip()

    # -------------------------------
    # CONFIRMATION HANDLING
    # -------------------------------
    if state.is_complete() and not state.confirmed:
        if message_lower in {"yes", "confirm", "okay", "ok"}:
            if not check_availability(state.date, state.time):
                state.reset()
                return "❌ That slot is no longer available."

            booking = book_appointment(state.date, state.time)
            state.reset()

            return (
                f"✅ Your appointment is confirmed!\n"
                f"📅 Date: {booking['date']}\n"
                f"⏰ Time: {booking['time']}"
            )

        if message_lower in {"no", "cancel"}:
            state.reset()
            return "Okay, I’ve cancelled the booking process."

        return (
            f"Please confirm:\n"
            f"📅 Date: {state.date}\n"
            f"⏰ Time: {state.time}\n"
            f"Reply with **yes** to confirm or **no** to cancel."
        )

    # -------------------------------
    # NORMAL EXTRACTION FLOW
    # -------------------------------
    extracted = extract_with_gemini(user_message)

    if extracted.get("intent") == "BOOK":
        state.intent = "BOOK"

    if extracted.get("date"):
        state.date = extracted["date"]

    if extracted.get("time"):
        if is_valid_time(extracted["time"]):
            state.time = extracted["time"]
        else:
            state.time = None

    # Ask missing info
    if state.intent == "BOOK" and not state.date:
        return "Sure 🙂 What date would you like to book?"

    if state.intent == "BOOK" and not state.time:
        return "Got it. What time should I book? (HH:MM format)"

    # Ask for confirmation
    if state.is_complete() and not state.confirmed:
        return (
            f"I can book an appointment on:\n"
            f"📅 Date: {state.date}\n"
            f"⏰ Time: {state.time}\n\n"
            f"Should I confirm?"
        )

    return "How can I help you today?"
