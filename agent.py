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
CONTROL_WORDS = {"yes", "no", "confirm", "ok", "okay"}


def is_valid_time(value: str | None) -> bool:
    return bool(value and TIME_PATTERN.match(value))


# -------------------------------
# Flexible time parsing (NO AI)
# -------------------------------
def parse_flexible_time(text: str) -> str | None:
    text = text.lower().strip()

    match = re.search(r"(\d{1,2})", text)
    if not match:
        return None

    hour = int(match.group(1))
    if hour < 1 or hour > 12:
        return None

    if "morning" in text:
        return f"{hour:02d}:00"
    if "afternoon" in text or "evening" in text or "night" in text:
        return f"{hour + 12:02d}:00"

    return None


# -------------------------------
# Gemini extraction (guarded)
# -------------------------------
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

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception:
        return None


# -------------------------------
# Agent main
# -------------------------------
def run_agent(user_message: str, state: BookingState) -> str:
    msg = user_message.strip()
    msg_lower = msg.lower()

    # --------------------------------
    # TIME CONFIRMATION HANDLING
    # --------------------------------
    if hasattr(state, "pending_time") and state.pending_time:
        if msg_lower in CONTROL_WORDS:
            state.time = state.pending_time
            state.pending_time = None
        else:
            state.pending_time = None
            return "Okay, please tell me the time again."

    # --------------------------------
    # NAME & PHONE CAPTURE (CONTEXT-AWARE)
    # --------------------------------
    if state.intent == "BOOK" and state.date and state.time:
        if state.patient_name is None:
            if msg_lower in CONTROL_WORDS:
                return "May I have the patient’s name?"
            state.patient_name = msg.title()
            return "Thanks. Please share a contact phone number."

        if state.patient_phone is None:
            digits = re.sub(r"\D", "", msg)
            if len(digits) == 10:
                state.patient_phone = digits
            else:
                return "Please enter a valid 10-digit phone number."

    # --------------------------------
    # FINAL CONFIRMATION
    # --------------------------------
    if state.is_complete():
        if msg_lower in {"yes", "confirm"}:
            if not check_availability(state.date, state.time):
                state.reset()
                return "❌ That slot is not available."

            booking = book_appointment(
                state.date,
                state.time,
                state.patient_name,
                state.patient_phone,
            )
            state.reset()

            return (
                f"✅ Your appointment is confirmed!\n"
                f"📅 Date: {booking['date']}\n"
                f"⏰ Time: {booking['time']}"
            )

        if msg_lower in {"no", "cancel"}:
            state.reset()
            return "Okay, I’ve cancelled the booking process."

        return (
            f"Please confirm:\n"
            f"📅 Date: {state.date}\n"
            f"⏰ Time: {state.time}\n"
            f"👤 Patient: {state.patient_name}\n"
            f"📞 Phone: {state.patient_phone}\n\n"
            f"Reply with yes or no."
        )

    # --------------------------------
    # FLEXIBLE TIME (RULE-BASED FIRST)
    # --------------------------------
    if state.intent == "BOOK" and state.date and not state.time:
        flexible = parse_flexible_time(msg)
        if flexible:
            state.pending_time = flexible
            return f"Do you mean {flexible}? Please confirm."

    # --------------------------------
    # GEMINI EXTRACTION (LAST RESORT)
    # --------------------------------
    extracted = extract_with_gemini(msg)
    if extracted is None:
        return "⚠️ I’m having trouble understanding right now. Please try again shortly."

    if extracted.get("intent") == "BOOK":
        state.intent = "BOOK"

    if extracted.get("date"):
        state.date = extracted["date"]

    if extracted.get("time") and is_valid_time(extracted["time"]):
        state.time = extracted["time"]

    # --------------------------------
    # ASK MISSING INFORMATION
    # --------------------------------
    if state.intent == "BOOK" and not state.date:
        return "Sure 🙂 What date would you like to book?"

    if state.intent == "BOOK" and not state.time:
        return "What time would you prefer? (e.g., 10 in the morning)"

    if state.intent == "BOOK" and not state.patient_name:
        return "May I have the patient’s name?"

    if state.intent == "BOOK" and not state.patient_phone:
        return "Please share a contact phone number."

    return "How can I help you today?"
