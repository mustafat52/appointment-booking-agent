# agent.py

import os
import json
import re
from datetime import datetime, timedelta

import google.generativeai as genai

from state import BookingState
from tools import check_availability, book_appointment, cancel_appointment
from doctor_config import DEFAULT_DOCTOR_ID


# ===============================
# Gemini Config
# ===============================
GENAI_API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "models/gemini-flash-latest")

genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel(MODEL_NAME)

CONTROL_WORDS = {"yes", "no", "confirm", "ok", "okay"}
CANCEL_KEYWORDS = {"cancel", "delete", "remove", "drop"}
RESCHEDULE_KEYWORDS = {"reschedule", "change", "move", "shift", "modify"}


# ===============================
# Helpers
# ===============================
def parse_flexible_time(text: str):
    text = text.lower()
    m = re.search(r"\b(\d{1,2})\b", text)
    if not m:
        return None

    hour = int(m.group(1))
    if hour < 1 or hour > 12:
        return None

    if "morning" in text:
        return f"{hour:02d}:00"
    if "afternoon" in text or "evening" in text or "night" in text:
        return f"{hour + 12:02d}:00"

    return None


def parse_flexible_date(text: str):
    today = datetime.today()
    text = text.lower()

    if "today" in text:
        return today.strftime("%Y-%m-%d")
    if "tomorrow" in text:
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")

    m = re.search(r"\b(\d{1,2})(st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", text)
    if not m:
        return None

    day = int(m.group(1))
    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
    }
    month = month_map[m.group(3)]
    year = today.year

    candidate = datetime(year, month, day)
    if candidate.date() < today.date():
        candidate = datetime(year + 1, month, day)

    return candidate.strftime("%Y-%m-%d")


def extract_intent_with_gemini(msg: str):
    prompt = f"""Return JSON only.
{{"intent":"BOOK|CANCEL|RESCHEDULE|UNKNOWN"}}
Message: {msg}"""
    try:
        r = model.generate_content(prompt).text
        return json.loads(r)["intent"]
    except Exception:
        return "UNKNOWN"


# ===============================
# Agent main
# ===============================
def run_agent(user_message: str, state: BookingState) -> str:
    msg = user_message.strip()
    msg_lower = msg.lower()
    doctor_id = state.doctor_id or DEFAULT_DOCTOR_ID

    # ---- intent detection
    if any(w in msg_lower for w in CANCEL_KEYWORDS):
        state.intent = "CANCEL"
    elif any(w in msg_lower for w in RESCHEDULE_KEYWORDS):
        state.intent = "RESCHEDULE"

    # ---- cancel flow
    if state.intent == "CANCEL":
        if not state.last_event_id:
            state.intent = None
            return "I couldn’t find a recent appointment to cancel."

        if msg_lower in CONTROL_WORDS:
            cancel_appointment(state.last_event_id, state.last_doctor_id)
            state.last_event_id = None
            state.last_doctor_id = None
            state.intent = None
            return "✅ Your appointment has been cancelled."

        return "Do you want to cancel your recent appointment? (yes / no)"

    # ---- reschedule flow
    if state.intent == "RESCHEDULE":
        if not state.last_event_id:
            state.intent = None
            return "I couldn’t find a recent appointment to reschedule."

        if not state.reschedule_date:
            d = parse_flexible_date(msg)
            if d:
                state.reschedule_date = d
            else:
                return "What new date would you like?"

        if not state.reschedule_time:
            t = parse_flexible_time(msg)
            if t:
                state.reschedule_time = t
            else:
                return "What new time would you prefer?"

        if msg_lower in CONTROL_WORDS:
            cancel_appointment(state.last_event_id, state.last_doctor_id)
            booking = book_appointment(
                state.reschedule_date,
                state.reschedule_time,
                doctor_id,
                state.patient_name,
                state.patient_phone,
            )
            state.last_event_id = booking["event_id"]
            state.last_doctor_id = doctor_id
            state.reset()
            return (
                f"✅ Rescheduled!\n📅 {booking['date']}\n⏰ {booking['time']}"
            )

        return (
            f"Please confirm reschedule:\n"
            f"📅 {state.reschedule_date}\n"
            f"⏰ {state.reschedule_time}\n(yes / no)"
        )

    # ---- booking flow
    if state.intent != "BOOK":
        state.intent = extract_intent_with_gemini(msg)

    if state.intent == "BOOK" and not state.date:
        d = parse_flexible_date(msg)
        if d:
            state.date = d
        else:
            return "Sure 🙂 What date would you like to book?"

    if state.intent == "BOOK" and not state.time:
        t = parse_flexible_time(msg)
        if t:
            state.time = t
        else:
            return "What time would you prefer?"

    if state.intent == "BOOK" and not state.patient_name:
        return "May I have the patient’s name?"

    if state.intent == "BOOK" and not state.patient_phone:
        digits = re.sub(r"\D", "", msg)
        if len(digits) == 10:
            state.patient_phone = digits
        else:
            return "Please enter a valid 10-digit phone number."

    if state.is_complete():
        if msg_lower in CONTROL_WORDS:
            if not check_availability(state.date, state.time, doctor_id):
                state.reset()
                return "❌ That slot is not available."

            booking = book_appointment(
                state.date,
                state.time,
                doctor_id,
                state.patient_name,
                state.patient_phone,
            )
            state.last_event_id = booking["event_id"]
            state.last_doctor_id = doctor_id
            state.confirmed = True
            state.reset()
            return (
                f"✅ Confirmed!\n📅 {booking['date']}\n⏰ {booking['time']}"
            )

        return (
            f"Please confirm:\n📅 {state.date}\n⏰ {state.time}\n"
            f"👤 {state.patient_name}\n📞 {state.patient_phone}\n(yes / no)"
        )

    return "How can I help you today?"
