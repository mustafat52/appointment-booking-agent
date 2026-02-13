from enum import Enum
from typing import Dict
from agent import run_agent
from state import BookingState
from db.database import SessionLocal
from db.repository import get_doctor_by_whatsapp_number, get_doctor_by_id





# --------------------------------------------------
# WhatsApp session stages
# --------------------------------------------------
class WhatsAppStage(Enum):
    START = "start"     # first contact
    MENU = "menu"       # numeric menu
    AGENT = "agent"     # free-form agent conversation


class WhatsAppSession:
    def __init__(self):
        self.stage: WhatsAppStage = WhatsAppStage.START
        self.booking_state: BookingState | None = None


# phone_number -> WhatsAppSession
whatsapp_state_store: Dict[str, WhatsAppSession] = {}


# --------------------------------------------------
# Menu config
# --------------------------------------------------
MENU_TEXT = (
    "Please choose an option:\n"
    "1️⃣ Book an appointment\n"
    "2️⃣ Cancel an appointment\n"
    "3️⃣ Reschedule an appointment\n"
    "0️⃣ Reset / Start over\n\n"
    "Reply with 1, 2, 3 or 0"
)

MENU_MAP = {
    "1": "BOOK",
    "2": "CANCEL",
    "3": "RESCHEDULE",
    "0": "RESET",
}



# --------------------------------------------------
# Main WhatsApp handler
# --------------------------------------------------
def handle_whatsapp_message(*, from_number: str, to_number: str, message_body: str) -> str:

    if from_number not in whatsapp_state_store:
        whatsapp_state_store[from_number] = WhatsAppSession()

    session = whatsapp_state_store[from_number]
    msg = message_body.strip()

    if session.stage == WhatsAppStage.START:

        # QR-based doctor routing
        if message_body.startswith("START_"):
            doctor_id = message_body.replace("START_", "").strip()

            db = SessionLocal()
            try:
                doctor = get_doctor_by_id(db, doctor_id)
            finally:
                db.close()

            if not doctor:
                return "⚠️ Invalid clinic link."

            state = BookingState()
            state.reset_flow()
            state.doctor_id = doctor.doctor_id
            state.doctor_name = doctor.name
            state.greeted = False

            session.booking_state = state
            session.stage = WhatsAppStage.MENU

            greeting = run_agent("", session.booking_state)
            return greeting + "\n\n" + MENU_TEXT

        # If user messages without QR entry
        return "⚠️ Please use your clinic's WhatsApp QR code to start booking."



    # MENU → numeric only
    if session.stage == WhatsAppStage.MENU:
        if msg not in MENU_MAP:
            return "❌ Invalid option.\n\n" + MENU_TEXT

        intent = MENU_MAP[msg]

        if intent == "reset":
            session.stage = WhatsAppStage.START
            session.booking_state = None
            return "🔄 Reset successful.\n\n" + MENU_TEXT

        session.stage = WhatsAppStage.AGENT
        return run_agent(intent, session.booking_state)

    # AGENT → free-form
    if session.stage == WhatsAppStage.AGENT:
        reply = run_agent(msg, session.booking_state)

        if session.booking_state.is_done():
            session.stage = WhatsAppStage.START
            session.booking_state = None
            return reply + "\n\n" + MENU_TEXT

        return reply
