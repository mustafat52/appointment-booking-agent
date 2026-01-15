import os
import json
import re
from datetime import date

import google.generativeai as genai

from state import BookingState
from tools import check_availability, book_appointment
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

# Phase 4.1 intent keywords
CANCEL_KEYWORDS = {"cancel", "delete", "remove", "drop"}
RESCHEDULE_KEYWORDS = {"reschedule", "change", "move", "shift", "modify"}


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
# Used ONLY if rule-based intent fails
# -------------------------------
def extract_intent_with_gemini(user_message: str):
    prompt = f"""
You are an intent classification system.

Return ONLY valid JSON.

Schema:
{{"intent": "BOOK | CANCEL | RESCHEDULE | UNKNOWN"}}

Message:
{user_message}
"""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        return data.get("intent", "UNKNOWN")
    except Exception:
        return "UNKNOWN"


# -------------------------------
# Agent main
# -------------------------------
def run_agent(user_message: str, state: BookingState) -> str:
    msg = user_message.strip()
    msg_lower = msg.lower()

    doctor_id = state.doctor_id or DEFAULT_DOCTOR_ID

    # ==================================================
    # PHASE 4.1 — INTENT DETECTION (RULE-BASED FIRST)
    # ==================================================
    if any(word in msg_lower for word in CANCEL_KEYWORDS):
        state.intent = "CANCEL"
        return (
            "I understand you want to cancel an appointment. "
            "I’ll help with that shortly."
        )

    if any(word in msg_lower for word in RESCHEDULE_KEYWORDS):
        state.intent = "RESCHEDULE"
        return (
            "I understand you want to reschedule an appointment. "
            "I’ll help with that shortly."
        )

    # ==================================================
    # TIME CONFIRMATION HANDLING
    # ==================================================
    if state.pending_time:
        if msg_lower in CONTROL_WORDS:
            state.time = state.pending_time
            state.pending_time = None
        else:
            state.pending_time = None
            return "Okay, please tell me the time again."

    # ==================================================
    # NAME & PHONE CAPTURE (BOOK FLOW)
    # ==================================================
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

    # ==================================================
    # FINAL CONFIRMATION (BOOK)
    # ==================================================
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

    # ==================================================
    # FLEXIBLE TIME (RULE-BASED)
    # ==================================================
    if state.intent == "BOOK" and state.date and not state.time:
        flexible = parse_flexible_time(msg)
        if flexible:
            state.pending_time = flexible
            return f"Do you mean {flexible}? Please confirm."

    # ==================================================
    # GEMINI FALLBACK — INTENT ONLY
    # ==================================================
    intent = extract_intent_with_gemini(msg)
    if intent in {"BOOK", "CANCEL", "RESCHEDULE"}:
        state.intent = intent

    # ==================================================
    # ASK MISSING INFORMATION (BOOK)
    # ==================================================
    if state.intent == "BOOK" and not state.date:
        return "Sure 🙂 What date would you like to book?"

    if state.intent == "BOOK" and not state.time:
        return "What time would you prefer? (e.g., 10 in the morning)"

    if state.intent == "BOOK" and not state.patient_name:
        return "May I have the patient’s name?"

    if state.intent == "BOOK" and not state.patient_phone:
        return "Please share a contact phone number."

    # CANCEL / RESCHEDULE placeholders (Phase 4.2+)
    if state.intent == "CANCEL":
        return "I’ll help you cancel your appointment shortly."

    if state.intent == "RESCHEDULE":
        return "I’ll help you reschedule your appointment shortly."

    return "How can I help you today?"
