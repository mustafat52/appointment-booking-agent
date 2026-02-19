import os
import logging
from twilio.rest import Client
from db.database import SessionLocal
from db.repository import get_doctor_by_id

logger = logging.getLogger("medschedule")

TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")

client = Client(TWILIO_SID, TWILIO_TOKEN)


def notify_doctor_via_whatsapp(
    *,
    doctor_id,
    message: str
):
    """
    Sends WhatsApp notification to doctor if:
    - notifications_enabled = True
    - doctor_whatsapp_number exists
    """

    db = SessionLocal()
    try:
        doctor = get_doctor_by_id(db, doctor_id)

        if not doctor:
            logger.warning("Doctor not found for notification")
            return

        if not doctor.notifications_enabled:
            logger.info(
                f"Notification skipped (trial mode) for doctor {doctor_id}"
            )
            return

        if not doctor.doctor_whatsapp_number:
            logger.warning(
                f"Doctor {doctor_id} has no WhatsApp number"
            )
            return

        client.messages.create(
            body=message,
            from_=f"whatsapp:{TWILIO_WHATSAPP_NUMBER}",
            to=f"whatsapp:{doctor.doctor_whatsapp_number}",
        )

        logger.info(
            f"Doctor notification sent | doctor_id={doctor_id}"
        )

    except Exception as e:
        logger.exception(
            f"Doctor notification failed | doctor_id={doctor_id} | {str(e)}"
        )
    finally:
        db.close()
