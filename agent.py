import os
import json
import re
from datetime import date

import google.generativeai as genai

from state import BookingState
from tools import (
    check_availability,
    book_appointment,
    cancel_appointment,
)
from doctor_config import DEFAULT_DOCTOR_ID


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

CANCEL_KEYWORDS = {"cancel", "delete", "remove", "drop"}
RESCHEDULE_KEYWORDS = {"reschedule", "change", "move", "shift", "modify"}


def is_valid_time(value: str | None) -> bool:
    return bool(value and TIME_PATTERN.match(value))


# -------------------------------
# Flexible time parsing (NO AI)
# -------------------------------
def parse_flexible_time(text: str) -> str | None:
    text = text.lower()

    match = re.search(r"(\d{1,2})", text)
    if not match:
        return None

    hour = int(match.group(1))
    if hour < 1 or hour > 12:
        return None

    if "morning" in text:
        return f"{hour:02d}:00"
    if any(w in text for w in {"afternoon", "evening", "night"}):
        return f"{hour + 12:02d}:00"

    return None


# -------------------------------
# Gemini intent fallback (LIGHT)
# -------------------------------
def extract_intent_with_gemini(message: str) -> str:
    prompt = f"""
Return intent as JSON.

Schema:
{{"intent": "BOOK | CANCEL | RESCHEDULE | UNKNOWN"}}

Message:
{message}
"""
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text).get("intent", "UNKNOWN")
    except Exception:
        return "UNKNOWN"


# ===============================
# AGENT MAIN
# ===============================
def run_agent(user_message: str, state: BookingState) -> str:
    msg = user_message.strip()
    msg_lower = msg.lower()

    doctor_id = state.doctor_id or DEFAULT_DOCTOR_ID

    # ==================================================
    # PHASE 4 — INTENT DETECTION (RULE FIRST)
    # ==================================================
    if any(k in msg_lower for k in CANCEL_KEYWORDS):
        state.intent = "CANCEL"

    elif any(k in msg_lower for k in RESCHEDULE_KEYWORDS):
        state.intent = "RESCHEDULE"

    elif state.intent is None:
        intent = extract_intent_with_gemini(msg)
        if intent in {"BOOK", "CANCEL", "RESCHEDULE"}:
            state.intent = intent

    # ==================================================
    # CANCEL FLOW
    # ==================================================
    if state.intent == "CANCEL":
        if not state.last_event_id:
            state.reset()
            return "I couldn’t find a recent appointment to cancel."

        if msg_lower in {"yes", "confirm"}:
            cancel_appointment(
                state.last_event_id,
                state.last_doctor_id or doctor_id,
            )
            state.reset()
            return "✅ Your appointment has been cancelled."

        return "Do you want to cancel your recent appointment? (yes / no)"

    # ==================================================
    # RESCHEDULE FLOW (Phase 4.4)
    # ==================================================
    if state.intent == "RESCHEDULE":
        if not state.last_event_id:
            state.reset()
            return "I couldn’t find a recent appointment to reschedule."

        if not state.reschedule_date:
            state.reschedule_date = None
            return "What new date would you like?"

        if not state.reschedule_time:
            flexible = parse_flexible_time(msg)
            if flexible:
                state.pending_time = flexible
                return f"Do you mean {flexible}? Please confirm."
            return "What new time would you prefer?"

        if msg_lower in {"yes", "confirm"}:
            # cancel old
            cancel_appointment(
                state.last_event_id,
                state.last_doctor_id or doctor_id,
            )

            # book new
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

    # ==================================================
    # TIME CONFIRMATION
    # ==================================================
    if state.pending_time:
        if msg_lower in CONTROL_WORDS:
            state.time = state.pending_time
            state.pending_time = None
        else:
            state.pending_time = None
            return "Okay, please tell me the time again."

    # ==================================================
    # BOOK FLOW (unchanged)
    # ==================================================
    if state.intent == "BOOK" and state.date and state.time:
        if not state.patient_name:
            state.patient_name = msg.title()
            return "Thanks. Please share a contact phone number."

        if not state.patient_phone:
            digits = re.sub(r"\D", "", msg)
            if len(digits) != 10:
                return "Please enter a valid 10-digit phone number."
            state.patient_phone = digits

    if state.is_complete():
        if msg_lower in {"yes", "confirm"}:
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

    # ==================================================
    # ASK MISSING (BOOK)
    # ==================================================
    if state.intent == "BOOK" and not state.date:
        return "Sure 🙂 What date would you like to book?"

    if state.intent == "BOOK" and not state.time:
        return "What time would you prefer? (e.g., 10 in the morning)"

    return "How can I help you today?"
