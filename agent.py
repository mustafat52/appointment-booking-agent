import os
import json
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


def extract_with_gemini(user_message: str):
    today = date.today().isoformat()

    prompt = f"""
You are an information extraction system.

TODAY'S DATE IS: {today}

Your job is to detect appointment booking intent.

Return ONLY valid JSON.

Schema:
{{"intent": "BOOK or UNKNOWN",
  "date": "YYYY-MM-DD or null",
  "time": "HH:MM or null"
}}

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

    if extracted["intent"] == "BOOK":
        state.intent = "BOOK"

    if extracted.get("date"):
        state.date = extracted["date"]

    if extracted.get("time"):
        state.time = extracted["time"]

    print("📦 STATE:", state.__dict__)

    if state.intent == "BOOK" and not state.date:
        return "Sure 🙂 What date would you like to book?"

    if state.intent == "BOOK" and not state.time:
        return "Got it. What time should I book?"

    if state.is_complete():
        if not check_availability(state.date, state.time):
            return "❌ That slot is not available. Please choose another time."

        booking = book_appointment(state.date, state.time)
        state.confirmed = True

        return (
            f"✅ Your appointment is confirmed!\n"
            f"📅 Date: {booking['date']}\n"
            f"⏰ Time: {booking['time']}"
        )

    return "How can I help you today?"
