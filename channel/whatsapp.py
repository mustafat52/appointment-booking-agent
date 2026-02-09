from enum import Enum
from typing import Dict
from agent import run_agent
from state import BookingState



TEST_DOCTOR_ID = "078b91b2-c31e-46af-bf3c-e77cf3dae63c"
TEST_DOCTOR_NAME = "Mustafa Taj"


def init_booking_state() -> BookingState:
    state = BookingState()
    state.reset_flow()
    state.doctor_id = TEST_DOCTOR_ID
    state.doctor_name = TEST_DOCTOR_NAME
    state.greeted = False
    return state



class WhatsAppStage(str, Enum):
    START = "START"
    MENU = "MENU"




class WhatsAppSession:
    def __init__(self):
        self.stage = WhatsAppStage.START
        self.booking_state: BookingState | None = None



# phone_number -> WhatsAppSession
whatsapp_state_store: Dict[str, WhatsAppSession] = {}


MENU_TEXT = (
    "👋 Welcome to MedSchedule AI\n\n"
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

def handle_whatsapp_message(
    *,
    from_number: str,
    message_body: str
) -> str:
    """
    Phase 3 handler:
    - show menu
    - accept numeric input
    - normalize intent
    - delegate to agent with hardcoded doctor
    """

    if from_number not in whatsapp_state_store:
        whatsapp_state_store[from_number] = WhatsAppSession()

    session = whatsapp_state_store[from_number]
    msg = message_body.strip()

    if session.stage == WhatsAppStage.START:
        session.stage = WhatsAppStage.MENU

        # Initialize booking state so agent can greet
        session.booking_state = init_booking_state()

        # Let agent produce the greeting
        greeting = run_agent("", session.booking_state)

        return greeting + "\n\n" + MENU_TEXT   #birmak greeting 


    # Menu stage → expect number
    if session.stage == WhatsAppStage.MENU:
        if msg not in MENU_MAP:
            return "❌ Invalid option.\n\n" + MENU_TEXT

        intent = MENU_MAP[msg]

        if intent == "reset":
            session.stage = WhatsAppStage.START
            session.booking_state = None
            return "🔄 Reset successful.\n\n" + MENU_TEXT

        # Initialize booking state once
        if session.booking_state is None:
            session.booking_state = init_booking_state()

        # Delegate to agent with normalized intent
        try:
            reply = run_agent(intent, session.booking_state)
        except Exception:
            session.booking_state.reset_flow()
            session.booking_state = None
            return (
                "⚠️ Something went wrong.\n"
                "Let’s start again.\n\n" + MENU_TEXT
            )

        return reply

    # Fallback safety
    session.stage = WhatsAppStage.START
    session.booking_state = None
    return MENU_TEXT
