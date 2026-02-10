from enum import Enum
from typing import Dict
from agent import run_agent
from state import BookingState

# --------------------------------------------------
# Temporary Phase-3 hardcoded doctor
# --------------------------------------------------
TEST_DOCTOR_ID = "078b91b2-c31e-46af-bf3c-e77cf3dae63c"
TEST_DOCTOR_NAME = "Mustafa Taj"


def init_booking_state() -> BookingState:
    state = BookingState()
    state.reset_flow()
    state.doctor_id = TEST_DOCTOR_ID
    state.doctor_name = TEST_DOCTOR_NAME
    state.greeted = False
    return state


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
    "1": "book",
    "2": "cancel",
    "3": "reschedule",
    "0": "reset",
}


# --------------------------------------------------
# Main WhatsApp handler
# --------------------------------------------------
def handle_whatsapp_message(*, from_number: str, message_body: str) -> str:
    if from_number not in whatsapp_state_store:
        whatsapp_state_store[from_number] = WhatsAppSession()

    session = whatsapp_state_store[from_number]
    msg = message_body.strip()

    # --------------------------------------------------
    # START → greet + menu (agent owns greeting)
    # --------------------------------------------------
    if session.stage == WhatsAppStage.START:
        session.stage = WhatsAppStage.MENU
        session.booking_state = init_booking_state()

        greeting = run_agent("", session.booking_state)
        return greeting + "\n\n" + MENU_TEXT

    # --------------------------------------------------
    # AGENT → agent owns ALL free-form messages
    # --------------------------------------------------
    if session.stage == WhatsAppStage.AGENT:
        try:
            reply = run_agent(msg, session.booking_state)
        except Exception:
            session.stage = WhatsAppStage.START
            session.booking_state = None
            return "⚠️ Something went wrong.\n\n" + MENU_TEXT

        # ✅ EXIT agent ONLY when state says done
        if session.booking_state and session.booking_state.is_done():
            session.stage = WhatsAppStage.START
            session.booking_state = None
            return reply + "\n\n" + MENU_TEXT

        return reply

    # --------------------------------------------------
    # MENU → numeric options ONLY
    # --------------------------------------------------
    if session.stage == WhatsAppStage.MENU:
        if msg not in MENU_MAP:
            return "❌ Invalid option.\n\n" + MENU_TEXT

        intent = MENU_MAP[msg]

        if intent == "reset":
            session.stage = WhatsAppStage.START
            session.booking_state = None
            return "🔄 Reset successful.\n\n" + MENU_TEXT

        # Move into agent mode
        session.stage = WhatsAppStage.AGENT
        return run_agent(intent, session.booking_state)

    # --------------------------------------------------
    # Safety fallback (should never happen)
    # --------------------------------------------------
    session.stage = WhatsAppStage.START
    session.booking_state = None
    return MENU_TEXT
