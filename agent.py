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
    # INTENT
    # ---------------------------
    if extracted["intent"]:
        state.intent = extracted["intent"]

    if state.intent is None:
        if any(w in msg for w in RESCHEDULE_KEYWORDS):
            state.intent = "RESCHEDULE"
        elif any(w in msg for w in CANCEL_KEYWORDS):
            state.intent = "CANCEL"
        elif any(w in msg for w in BOOK_KEYWORDS):
            state.intent = "BOOK"

    if state.intent is None:
        return "Hello 🙂 How can I help you today?"

    # ---------------------------
    # CANCEL
    # ---------------------------
    if state.intent == "CANCEL":
        if not state.last_event_id:
            state.reset()
            return "I couldn’t find any recent appointment to cancel."

        if msg in CONTROL_WORDS:
            cancel_appointment(state.last_event_id, state.last_doctor_id)
            state.reset()
            return "✅ Your appointment has been cancelled."

        return "Do you want to cancel your recent appointment? (yes / no)"

    # ---------------------------
    # RESCHEDULE (FIXED)
    # ---------------------------
    if state.intent == "RESCHEDULE":
        if not state.last_event_id:
            state.reset()
            return "I couldn’t find any appointment to reschedule."

        # --- Handle "same day" / "same time"
        if any(p in msg for p in ["same day", "same date"]):
            state.reschedule_date = state.date

        if "same time" in msg:
            state.reschedule_time = state.time    




        elif not state.reschedule_date:
            parsed = normalize_date(msg)
            if parsed:
                state.reschedule_date = parsed

        if "same time" in msg:
            state.reschedule_time = state.time
        elif not state.reschedule_time:
            t, _ = normalize_time(msg)
            if t:
                state.reschedule_time = t

        if not state.reschedule_date:
            return "What new date would you like?"

        if not state.reschedule_time:
            return "What new time would you prefer?"

        # --- Check availability BEFORE confirm
        if not check_availability(state.reschedule_date, state.reschedule_time, doctor_id):
            state.reschedule_date = None
            state.reschedule_time = None
            return "❌ That slot is not available. Please choose another date or time."

        if msg in CONTROL_WORDS:
            # 🔥 ACTUAL RESCHEDULE = cancel + book
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
            state.date = booking["date"]
            state.time = booking["time"]
            state.reschedule_date = None
            state.reschedule_time = None
            state.intent = None

            return f"✅ Appointment rescheduled to {booking['date']} at {booking['time']}"

        return (
            f"Please confirm reschedule:\n"
            f"📅 {state.reschedule_date}\n"
            f"⏰ {state.reschedule_time}\n"
            f"(yes / no)"
        )

    # ---------------------------
    # BOOK (UNCHANGED)
    # ---------------------------
    if not state.date:
        parsed = normalize_date(msg)
        if parsed:
            state.date = parsed
        else:
            state.expecting = "date"
            return "What date would you like to book?"

    if not state.time:
        t, _ = normalize_time(msg)
        if t:
            state.time = t
        else:
            state.expecting = "time"
            return "Could you please specify the exact time?"

    if not check_availability(state.date, state.time, doctor_id):
        state.date = None
        state.time = None
        state.expecting = "date"
        return "❌ That slot is not available. Please choose another date and time."

    if not state.patient_name:
        if state.expecting != "name":
            state.expecting = "name"
            return "May I know the patient’s name?"
        state.patient_name = user_message.strip().title()

    if not state.patient_phone:
        digits = re.sub(r"\D", "", msg)
        if len(digits) == 10:
            state.patient_phone = digits
        else:
            state.expecting = "phone"
            return "Please share a 10-digit contact number."

    state.expecting = "confirm"

    if msg in CONTROL_WORDS:
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
