import os
import json
import re
from datetime import date

import google.generativeai as genai

from state import BookingState
from tools import check_availability, book_appointment


# ===============================
# Gemini / Google AI (ENV ONLY)
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
    except Exception as e:
        print("❌ Gemini parse error:", e)
        print("❌ Raw output:", response.text)
        return {"intent": "UNKNOWN", "date": None, "time": None}


def run_agent(user_message: str, state: BookingState) -> str:
    extracted = extract_with_gemini(user_message)
    print("🧠 EXTRACTED:", extracted)

    # Intent
    if extracted.get("intent") == "BOOK":
        state.intent = "BOOK"

    # Date
    if extracted.get("date"):
        state.date = extracted["date"]

    # Time (STRICT)
    if extracted.get("time"):
        if is_valid_time(extracted["time"]):
            state.time = extracted["time"]
        else:
            state.time = None  # 🔥 CRITICAL FIX

    print("📦 STATE:", state.__dict__)

    # Ask missing info
    if state.intent == "BOOK" and not state.date:
        return "Sure 🙂 What date would you like to book?"

    if state.intent == "BOOK" and not state.time:
        return "Got it. What time should I book? (e.g., 15:00)"

    # Final booking
    if state.is_complete():
        print("🔍 FINAL CHECK:", state.date, state.time)

        if not check_availability(state.date, state.time):
            return "❌ That slot is not available or outside working hours."

        booking = book_appointment(state.date, state.time)
        state.confirmed = True

        return (
            f"✅ Your appointment is confirmed!\n"
            f"📅 Date: {booking['date']}\n"
            f"⏰ Time: {booking['time']}"
        )

    return "How can I help you today?"
