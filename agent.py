# agent.py

import re
from datetime import datetime, timedelta

from extractor import extract_entities
from state import BookingState
from tools import check_availability, book_appointment, cancel_appointment
from doctor_config import DEFAULT_DOCTOR_ID


CONTROL_WORDS = {"yes", "no", "confirm", "ok", "okay"}

BOOK_KEYWORDS = {"book", "appointment", "schedule"}
CANCEL_KEYWORDS = {"cancel", "delete", "remove", "drop"}
RESCHEDULE_KEYWORDS = {"reschedule", "change", "move", "shift", "modify"}


# ---------------------------
# Normalization helpers
# ---------------------------

def normalize_time(text: str):
    if not text:
        return None, False

    t = text.lower()
    m = re.search(r"\b(\d{1,2})\b", t)
    if not m:
        return None, True

    hour = int(m.group(1))

    if "morning" in t:
        return ("00:00" if hour == 12 else f"{hour:02d}:00"), False

    if "afternoon" in t or "evening" in t or "pm" in t:
        if hour < 12:
            hour += 12
        return f"{hour:02d}:00", False

    if "am" in t:
        return ("00:00" if hour == 12 else f"{hour:02d}:00"), False

    return None, True


def normalize_date(text: str):
    if not text:
        return None

    t = text.lower()
    today = datetime.today()

    if "today" in t:
        return today.strftime("%Y-%m-%d")

    if "tomorrow" in t:
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")

    months = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]

    m1 = re.search(
        r"\b(\d{1,2})(st|nd|rd|th)?\b.*(" + "|".join(months) + r")",
        t
    )
    m2 = re.search(
        r"\b(" + "|".join(months) + r")\b.*(\d{1,2})(st|nd|rd|th)?",
        t
    )

    if m1:
        day = int(m1.group(1))
        month = months.index(m1.group(3)) + 1
    elif m2:
        day = int(m2.group(2))
        month = months.index(m2.group(1)) + 1
    else:
        return None

    year = today.year
    try:
        d = datetime(year, month, day)
        if d.date() < today.date():
            d = datetime(year + 1, month, day)
        return d.strftime("%Y-%m-%d")
    except:
        return None


# ---------------------------
# Main Agent
# ---------------------------

def run_agent(user_message: str, state: BookingState) -> str:
    msg = user_message.strip().lower()
    doctor_id = state.doctor_id or DEFAULT_DOCTOR_ID

    extracted = extract_entities(user_message)

    # ---------------------------
    # INTENT (LLM + FALLBACK)
    # ---------------------------
    if extracted["intent"]:
        state.intent = extracted["intent"]

    if state.intent is None:
        if any(w in msg for w in BOOK_KEYWORDS):
            state.intent = "BOOK"
        elif any(w in msg for w in CANCEL_KEYWORDS):
            state.intent = "CANCEL"
        elif any(w in msg for w in RESCHEDULE_KEYWORDS):
            state.intent = "RESCHEDULE"

    if state.intent is None:
        return "Hello 🙂 How can I help you today?"

    # ---------------------------
    # NAME (ONLY IF MISSING)
    # ---------------------------
    if not state.patient_name and extracted["patient_name"]:
        if extracted["patient_name"].lower() not in CONTROL_WORDS:
            state.patient_name = extracted["patient_name"].title()

    # ---------------------------
    # PHONE (ONLY IF MISSING)
    # ---------------------------
    if not state.patient_phone and extracted["patient_phone"]:
        digits = re.sub(r"\D", "", extracted["patient_phone"])
        if len(digits) == 10:
            state.patient_phone = digits

    # ---------------------------
    # DATE (ONLY IF NOT SET)
    # ---------------------------
    if state.intent == "BOOK" and not state.date:
        date_source = extracted["date_text"] or msg
        parsed_date = normalize_date(date_source)
        if parsed_date:
            state.date = parsed_date

    if state.intent == "RESCHEDULE" and not state.reschedule_date:
        date_source = extracted["date_text"] or msg
        parsed_date = normalize_date(date_source)
        if parsed_date:
            state.reschedule_date = parsed_date

    # ---------------------------
    # TIME (ONLY IF NOT SET)
    # ---------------------------
    if state.intent == "BOOK" and not state.time:
        time_source = extracted["time_text"] or msg
        time_value, ambiguous = normalize_time(time_source)

        if time_value:
            state.time = time_value
            state.awaiting_clarification = False
        elif ambiguous:
            state.awaiting_clarification = True

    if state.intent == "RESCHEDULE" and not state.reschedule_time:
        time_source = extracted["time_text"] or msg
        time_value, ambiguous = normalize_time(time_source)

        if time_value:
            state.reschedule_time = time_value
            state.awaiting_clarification = False
        elif ambiguous:
            state.awaiting_clarification = True

    # ---------------------------
    # CANCEL
    # ---------------------------
    if state.intent == "CANCEL":
        if not state.last_event_id:
            state.reset()
            return "I couldn’t find any recent appointment to cancel."

        if msg in CONTROL_WORDS:
            cancel_appointment(state.last_event_id, state.last_doctor_id)
            state.last_event_id = None
            state.last_doctor_id = None
            state.reset()
            return "✅ Your appointment has been cancelled."

        return "Do you want to cancel your recent appointment? (yes / no)"

    # ---------------------------
    # RESCHEDULE
    # ---------------------------
    if state.intent == "RESCHEDULE":
        if not state.last_event_id:
            state.reset()
            return "I couldn’t find any appointment to reschedule."

        if not state.reschedule_date:
            return "What new date would you like?"

        if not state.reschedule_time:
            return "What new time would you prefer?"

        if msg in CONTROL_WORDS:
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

    # ---------------------------
    # BOOK
    # ---------------------------
    if not state.date:
        return "What date would you like to book?"

    if state.awaiting_clarification or not state.time:
        state.awaiting_clarification = False
        return "Could you please specify the exact time?"

    if not state.patient_name:
        return "May I know the patient’s name?"

    if not state.patient_phone:
        return "Please share a 10-digit contact number."

    if msg in CONTROL_WORDS:
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
