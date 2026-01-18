# agent.py

import re
from datetime import datetime, timedelta

from extractor import extract_entities
from state import BookingState
from tools import check_availability, book_appointment, cancel_appointment
from doctor_config import DEFAULT_DOCTOR_ID


CONTROL_WORDS = {"yes", "no", "confirm", "ok", "okay"}


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

    # ✅ FIX: handle 4th, 21st, etc.
    m = re.search(
        r"\b(\d{1,2})(st|nd|rd|th)?\b.*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
        t
    )
    if m:
        day = int(m.group(1))
        month = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"].index(m.group(3)) + 1
        year = today.year
        try:
            d = datetime(year, month, day)
            if d.date() < today.date():
                d = datetime(year + 1, month, day)
            return d.strftime("%Y-%m-%d")
        except:
            return None

    return None


# ---------------------------
# Main Agent
# ---------------------------

def run_agent(user_message: str, state: BookingState) -> str:
    print("\n================ NEW TURN ================")
    print("👤 USER:", user_message)
    print("📦 STATE BEFORE:", state.__dict__)

    msg = user_message.strip().lower()
    doctor_id = state.doctor_id or DEFAULT_DOCTOR_ID

    extracted = extract_entities(user_message)

    # ---- STATE MERGE ----
    if extracted["intent"]:
        state.intent = extracted["intent"]

    if extracted["patient_name"] and not state.patient_name:
        # avoid control words being treated as names
        if extracted["patient_name"].lower() not in CONTROL_WORDS:
            state.patient_name = extracted["patient_name"].title()

    if extracted["patient_phone"] and not state.patient_phone:
        digits = re.sub(r"\D", "", extracted["patient_phone"])
        if len(digits) == 10:
            state.patient_phone = digits

    if extracted["date_text"]:
        parsed_date = normalize_date(extracted["date_text"])
        if parsed_date:
            if state.intent == "RESCHEDULE":
                state.reschedule_date = parsed_date
            else:
                state.date = parsed_date

    if extracted["time_text"]:
        time_value, ambiguous = normalize_time(extracted["time_text"])
        if ambiguous:
            state.awaiting_clarification = True
        elif time_value:
            if state.intent == "RESCHEDULE":
                state.reschedule_time = time_value
            else:
                state.time = time_value

    print("📦 STATE AFTER MERGE:", state.__dict__)

    # ---------------------------
    # ✅ INTENT GATE (CRITICAL FIX)
    # ---------------------------
    if state.intent is None:
        response = "Hello 🙂 How can I help you today?"
        print("🤖 RESPONSE:", response)
        return response

    # ---------------------------
    # CANCEL
    # ---------------------------
    if state.intent == "CANCEL":
        if not state.last_event_id:
            state.reset()
            response = "I couldn’t find any recent appointment to cancel."
            print("🤖 RESPONSE:", response)
            return response

        if msg in CONTROL_WORDS:
            cancel_appointment(state.last_event_id, state.last_doctor_id)
            state.last_event_id = None
            state.last_doctor_id = None
            state.reset()
            response = "✅ Your appointment has been cancelled."
            print("🤖 RESPONSE:", response)
            return response

        response = "Do you want to cancel your recent appointment? (yes / no)"
        print("🤖 RESPONSE:", response)
        return response

    # ---------------------------
    # RESCHEDULE
    # ---------------------------
    if state.intent == "RESCHEDULE":
        if not state.last_event_id:
            state.reset()
            response = "I couldn’t find any appointment to reschedule."
            print("🤖 RESPONSE:", response)
            return response

        if not state.reschedule_date:
            response = "What new date would you like?"
            print("🤖 RESPONSE:", response)
            return response

        if not state.reschedule_time:
            response = "What new time would you prefer?"
            print("🤖 RESPONSE:", response)
            return response

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
            response = f"✅ Rescheduled to {booking['date']} at {booking['time']}"
            print("🤖 RESPONSE:", response)
            return response

        response = (
            f"Please confirm reschedule:\n"
            f"📅 {state.reschedule_date}\n"
            f"⏰ {state.reschedule_time}\n"
            f"(yes / no)"
        )
        print("🤖 RESPONSE:", response)
        return response

    # ---------------------------
    # BOOK (PROPERLY GUARDED)
    # ---------------------------
    if state.intent == "BOOK":

        if not state.date:
            response = "What date would you like to book?"
            print("🤖 RESPONSE:", response)
            return response

        if state.awaiting_clarification or not state.time:
            state.awaiting_clarification = False
            response = "Could you please specify the exact time?"
            print("🤖 RESPONSE:", response)
            return response

        if not state.patient_name:
            response = "May I know the patient’s name?"
            print("🤖 RESPONSE:", response)
            return response

        if not state.patient_phone:
            response = "Please share a 10-digit contact number."
            print("🤖 RESPONSE:", response)
            return response

        if msg in CONTROL_WORDS:
            if not check_availability(state.date, state.time, doctor_id):
                state.reset()
                response = "❌ That slot is not available."
                print("🤖 RESPONSE:", response)
                return response

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
            response = f"✅ Appointment booked for {booking['date']} at {booking['time']}"
            print("🤖 RESPONSE:", response)
            return response

        response = (
            f"Please confirm:\n"
            f"📅 {state.date}\n"
            f"⏰ {state.time}\n"
            f"👤 {state.patient_name}\n"
            f"📞 {state.patient_phone}\n"
            f"(yes / no)"
        )
        print("🤖 RESPONSE:", response)
        return response
