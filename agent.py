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


# ===============================
# Constants
# ===============================
CONTROL_WORDS = {"yes", "no", "confirm", "ok", "okay"}
CANCEL_KEYWORDS = {"cancel", "delete", "remove", "drop"}
RESCHEDULE_KEYWORDS = {"reschedule", "change", "move", "shift", "modify"}


# ===============================
# Helpers
# ===============================
def parse_time(text: str):
    text = text.lower()
    m = re.search(r"\b(\d{1,2})\b", text)
    if not m:
        return None
    h = int(m.group(1))
    if h < 1 or h > 12:
        return None
    if "pm" in text or "afternoon" in text or "evening" in text:
        return f"{h+12:02d}:00"
    return f"{h:02d}:00"


def parse_date(text: str):
    text = text.lower()
    today = datetime.today()

    if "today" in text:
        return today.strftime("%Y-%m-%d")
    if "tomorrow" in text:
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")

    m = re.search(r"\b(\d{1,2})\b.*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", text)
    if m:
        day = int(m.group(1))
        month = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"].index(m.group(2)) + 1
        year = today.year
        try:
            d = datetime(year, month, day)
            if d.date() < today.date():
                d = datetime(year + 1, month, day)
            return d.strftime("%Y-%m-%d")
        except:
            return None
    return None


# ===============================
# Main Agent
# ===============================
def run_agent(user_message: str, state: BookingState) -> str:
    msg = user_message.strip()
    msg_lower = msg.lower()
    doctor_id = state.doctor_id or DEFAULT_DOCTOR_ID

    # ---------------------------
    # Neutral greetings
    # ---------------------------
    if state.intent is None and msg_lower in {"hi", "hello", "hey"}:
        return "Hello 🙂 How can I help you?"

    # ---------------------------
    # Intent detection (SAFE)
    # ---------------------------
# ===============================
# INTENT DETECTION (SAFE)
# ===============================
    if state.intent is None:
        if any(w in msg_lower for w in CANCEL_KEYWORDS):
            state.intent = "CANCEL"

        elif any(w in msg_lower for w in RESCHEDULE_KEYWORDS):
            state.intent = "RESCHEDULE"

        elif any(word in msg_lower for word in ["book", "appointment", "schedule"]):
            state.intent = "BOOK"

        else:
            return "Hello 🙂 How can I help you?"

    # ===========================
    # CANCEL
    # ===========================
    if state.intent == "CANCEL":
        if not state.last_event_id:
            state.intent = None
            return "I couldn’t find any recent appointment to cancel."

        if msg_lower in CONTROL_WORDS:
            cancel_appointment(state.last_event_id, state.last_doctor_id)
            state.last_event_id = None
            state.last_doctor_id = None
            state.intent = None
            return "✅ Your appointment has been cancelled."

        return "Do you want to cancel your recent appointment? (yes / no)"

    # ===========================
    # RESCHEDULE
    # ===========================
    if state.intent == "RESCHEDULE":
        if not state.last_event_id:
            state.intent = None
            return "I couldn’t find any appointment to reschedule."

        if not state.reschedule_date:
            d = parse_date(msg)
            if d:
                state.reschedule_date = d
            else:
                return "What new date would you like?"

        if not state.reschedule_time:
            t = parse_time(msg)
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
            return f"✅ Rescheduled to {booking['date']} at {booking['time']}"

        return (
            f"Please confirm reschedule:\n"
            f"📅 {state.reschedule_date}\n"
            f"⏰ {state.reschedule_time}\n"
            f"(yes / no)"
        )

    # ===========================
    # BOOK
    # ===========================
    if not state.date:
        d = parse_date(msg)
        if d:
            state.date = d
        else:
            return "What date would you like to book?"

    if not state.time:
        t = parse_time(msg)
        if t:
            state.time = t
        else:
            return "What time would you prefer?"

    if not state.patient_name:
        if msg_lower in CONTROL_WORDS:
            return "Please tell me the patient’s name."
        state.patient_name = msg.title()
        return "Please share a contact phone number."

    if not state.patient_phone:
        digits = re.sub(r"\D", "", msg)
        if len(digits) != 10:
            return "Please enter a valid 10-digit phone number."
        state.patient_phone = digits

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
        return f"✅ Appointment booked for {booking['date']} at {booking['time']}"

    return (
        f"Please confirm:\n"
        f"📅 {state.date}\n"
        f"⏰ {state.time}\n"
        f"👤 {state.patient_name}\n"
        f"📞 {state.patient_phone}\n"
        f"(yes / no)"
    )
