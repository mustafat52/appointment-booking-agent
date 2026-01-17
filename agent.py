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

if not GENAI_API_KEY:
    raise RuntimeError("GOOGLE_GEMINI_API_KEY is not set")

genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel(MODEL_NAME)

CONTROL_WORDS = {"yes", "no", "confirm", "ok", "okay"}
BOOK_KEYWORDS = {"book", "appointment", "schedule"}
CANCEL_KEYWORDS = {"cancel", "delete", "remove", "drop"}
RESCHEDULE_KEYWORDS = {"reschedule", "change", "move", "shift", "modify"}

# ===============================
# Time parsing
# ===============================
def parse_flexible_time(text: str):
    text = text.lower()
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

# ===============================
# Date parsing
# ===============================
MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

def parse_flexible_date(text: str):
    text = text.lower()
    today = datetime.today()

    if "today" in text:
        return today.strftime("%Y-%m-%d")
    if "tomorrow" in text:
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    if "day after tomorrow" in text:
        return (today + timedelta(days=2)).strftime("%Y-%m-%d")

    for name, month in MONTHS.items():
        if name in text:
            day_match = re.search(r"\b(\d{1,2})", text)
            if not day_match:
                return None
            day = int(day_match.group(1))
            year = today.year
            try:
                candidate = datetime(year, month, day)
                if candidate.date() < today.date():
                    candidate = datetime(year + 1, month, day)
                return candidate.strftime("%Y-%m-%d")
            except ValueError:
                return None

    return None

# ===============================
# Gemini intent fallback (last)
# ===============================
def extract_intent_with_gemini(message: str):
    prompt = f"""
Return ONLY JSON.

Schema:
{{"intent": "BOOK | CANCEL | RESCHEDULE | UNKNOWN"}}

Message:
{message}
"""
    try:
        resp = model.generate_content(prompt)
        text = resp.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text).get("intent", "UNKNOWN")
    except Exception:
        return "UNKNOWN"

# ===============================
# Agent
# ===============================
def run_agent(user_message: str, state: BookingState) -> str:
    msg = user_message.strip()
    msg_lower = msg.lower()

    doctor_id = state.doctor_id or DEFAULT_DOCTOR_ID

    # --------------------------------
    # Intent detection (LOCKED)
    # --------------------------------
    if state.intent is None:
        if any(w in msg_lower for w in CANCEL_KEYWORDS):
            state.intent = "CANCEL"
        elif any(w in msg_lower for w in RESCHEDULE_KEYWORDS):
            state.intent = "RESCHEDULE"
        elif any(w in msg_lower for w in BOOK_KEYWORDS):
            state.intent = "BOOK"

    # --------------------------------
    # CANCEL FLOW
    # --------------------------------
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

    # --------------------------------
    # RESCHEDULE FLOW (4.4)
    # --------------------------------
    if state.intent == "RESCHEDULE":
        if not state.last_event_id:
            state.intent = None
            return "I couldn’t find a recent appointment to reschedule."

        if state.reschedule_date is None:
            parsed = parse_flexible_date(msg)
            if parsed:
                state.reschedule_date = parsed
            else:
                return "What new date would you like?"

        if state.reschedule_time is None:
            parsed_time = parse_flexible_time(msg)
            if parsed_time:
                state.reschedule_time = parsed_time
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
                "✅ Your appointment has been rescheduled!\n"
                f"📅 Date: {booking['date']}\n"
                f"⏰ Time: {booking['time']}"
            )

        return (
            f"Please confirm reschedule:\n"
            f"📅 Date: {state.reschedule_date}\n"
            f"⏰ Time: {state.reschedule_time}\n\n"
            f"Reply with yes or no."
        )

    # --------------------------------
    # BOOK FLOW
    # --------------------------------
    if state.intent == "BOOK" and not state.date:
        parsed = parse_flexible_date(msg)
        if parsed:
            state.date = parsed
        else:
            return "What date would you like to book?"

    if state.intent == "BOOK" and state.date and not state.time:
        parsed_time = parse_flexible_time(msg)
        if parsed_time:
            state.pending_time = parsed_time
            return f"Do you mean {parsed_time}? Please confirm."
        return "What time would you prefer?"

    if state.pending_time:
        if msg_lower in CONTROL_WORDS:
            state.time = state.pending_time
            state.pending_time = None
        else:
            state.pending_time = None
            return "Okay, please tell me the time again."

    if state.intent == "BOOK" and state.date and state.time:
        if state.patient_name is None:
            if parse_flexible_time(msg) or parse_flexible_date(msg):
                return "May I have the patient’s name?"
            if msg_lower in CONTROL_WORDS:
                return "May I have the patient’s name?"
            state.patient_name = msg.title()
            return "Please share a contact phone number."

        if state.patient_phone is None:
            digits = re.sub(r"\D", "", msg)
            if len(digits) != 10:
                return "Please enter a valid 10-digit phone number."
            state.patient_phone = digits

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
            state.reset()
            return (
                f"✅ Your appointment is confirmed!\n"
                f"📅 Date: {booking['date']}\n"
                f"⏰ Time: {booking['time']}"
            )

        return (
            f"Please confirm:\n"
            f"📅 Date: {state.date}\n"
            f"⏰ Time: {state.time}\n"
            f"👤 Patient: {state.patient_name}\n"
            f"📞 Phone: {state.patient_phone}\n\n"
            f"Reply with yes or no."
        )

    return "How can I help you today?"
