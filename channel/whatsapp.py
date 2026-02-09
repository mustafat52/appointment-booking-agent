from enum import Enum
from typing import Dict


class WhatsAppStage(str, Enum):
    START = "START"
    MENU = "MENU"


class WhatsAppSession:
    def __init__(self):
        self.stage = WhatsAppStage.START


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
    Phase 2 handler:
    - show menu
    - accept numeric input
    - normalize intent
    - NO agent call yet
    """

    if from_number not in whatsapp_state_store:
        whatsapp_state_store[from_number] = WhatsAppSession()

    session = whatsapp_state_store[from_number]
    msg = message_body.strip()

    # First interaction → show menu
    if session.stage == WhatsAppStage.START:
        session.stage = WhatsAppStage.MENU
        return MENU_TEXT

    # Menu stage → expect number
    if session.stage == WhatsAppStage.MENU:
        if msg not in MENU_MAP:
            return (
                "❌ Invalid option.\n\n"
                + MENU_TEXT
            )

        intent = MENU_MAP[msg]

        if intent == "reset":
            session.stage = WhatsAppStage.START
            return "🔄 Reset successful.\n\n" + MENU_TEXT

        # Phase-2 stop point
        return (
            f"✅ You selected *{intent.upper()}*.\n\n"
            "⚠️ Booking flow will be enabled next.\n"
            "For now, this confirms menu handling works."
        )

    # Fallback (should never hit)
    session.stage = WhatsAppStage.START
    return MENU_TEXT
