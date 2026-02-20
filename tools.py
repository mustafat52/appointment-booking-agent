from datetime import datetime, timedelta
import pytz
import os

from calendar_oauth import build_calendar_service
from auth_store import oauth_store

# LEGACY (fallback only – do not add new logic here)
from doctor_config import DOCTORS, DEFAULT_DOCTOR_ID
from sqlalchemy import false, select
from db.database import SessionLocal
from db.models import DoctorCalendarCredential
from services.notification_service import notify_doctor_via_whatsapp



from db.repository import (
    create_patient,
    create_appointment,
    get_appointment_by_event_id,
    cancel_appointment_db,
    reschedule_appointment_db,
    get_doctor_by_id,
    get_appointment_by_id,
    get_doctor_by_id
)

TIMEZONE = "Asia/Kolkata"
DISABLE_CALENDAR = os.getenv("DISABLE_CALENDAR", "false").lower() == "true"






def get_credentials_for_doctor(doctor_id):
    """
    Phase 8 – DB-first calendar credentials lookup.
    Falls back to in-memory store for safety.
    """
    from db.repository import get_doctor_calendar_credentials

    doctor_id_str = str(doctor_id)

    # 1️⃣ DB-first
    creds_row = get_doctor_calendar_credentials(doctor_id)
    if creds_row:
        from google.oauth2.credentials import Credentials

        return Credentials(
            token=creds_row.access_token,
            refresh_token=creds_row.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            scopes=["https://www.googleapis.com/auth/calendar"],
            expiry=creds_row.expires_at,
        )

    # 2️⃣ Fallback to in-memory (temporary safety net)
    creds_map = oauth_store.get("credentials", {})
    return creds_map.get(doctor_id_str)





# ------------------------------------------------------------------
# LEGACY CONFIG-BASED DOCTOR FETCH (FALLBACK ONLY)
# ------------------------------------------------------------------
def _get_doctor(doctor_id: str):
    """
    ⚠️ LEGACY FALLBACK
    Do NOT add new logic dependencies on this.
    Will be removed in Phase 7.
    """
    return DOCTORS.get(doctor_id, DOCTORS[DEFAULT_DOCTOR_ID])


# ------------------------------------------------------------------
# Phase 6.6 – DB-backed doctor fetch (SAFE, ADDITIVE)
# ------------------------------------------------------------------
def get_doctor_from_db(doctor_id):
    """
    DB-first doctor fetch.
    Returns None if not found or DB error.
    """
    db = None
    try:
        from db.database import SessionLocal
        from db.models import Doctor

        db = SessionLocal()
        return db.get(Doctor, doctor_id)
    except Exception:
        return None
    finally:
        if db:
            db.close()


# ------------------------------------------------------------------
# Phase 6.6.3 – DB-first calendar identity (SAFE)
# ------------------------------------------------------------------
def get_calendar_id_for_doctor(doctor_id):
    with SessionLocal() as db:
        creds = db.execute(
            select(DoctorCalendarCredential).where(
                DoctorCalendarCredential.doctor_id == doctor_id
            )
        ).scalars().first()

        if not creds:
            raise RuntimeError("❌ No calendar credentials found for doctor")

        return creds.calendar_id or "primary"



# ------------------------------------------------------------------
# Phase 6.6 – DB-based availability (SAFE, ADDITIVE)
# ------------------------------------------------------------------
def check_availability_db(
    date_str: str,
    time_str: str,
    doctor_id,
    exclude_appointment_id=None,
):
    """
    DB-only availability check.
    Returns True if slot is free, False if overlap exists.
    Never touches Google Calendar.
    """

    from db.database import SessionLocal
    from db.models import Appointment

    db = SessionLocal()
    try:
        q = db.query(Appointment).filter(
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date == datetime.strptime(date_str, "%Y-%m-%d").date(),
            Appointment.appointment_time == datetime.strptime(time_str, "%H:%M").time(),
            Appointment.status == "BOOKED",
        )

        if exclude_appointment_id:
            q = q.filter(Appointment.appointment_id != exclude_appointment_id)

        return not db.query(q.exists()).scalar()

    finally:
        db.close()



# ------------------------------------------------------------------
# Availability entry point (DB-first, LEGACY fallback preserved)
# ------------------------------------------------------------------
def check_availability(
    date_str: str,
    time_str: str,
    doctor_id: str,
    exclude_appointment_id=None,
) -> bool:
    try:
        return check_availability_db(
            date_str,
            time_str,
            doctor_id,
            exclude_appointment_id=exclude_appointment_id,
        )
    except Exception:
        # Fail closed: safer to block than double-book
        return False


# ------------------------------------------------------------------
# Booking (calendar now DB-first, logic unchanged otherwise)
# ------------------------------------------------------------------
def book_appointment(date_str, time_str, doctor_id, patient_name, patient_phone):
    if not doctor_id:
        raise ValueError("Doctor context missing during booking")

    db = SessionLocal()
    try:
        doctor_db = get_doctor_by_id(db,doctor_id)
        if not doctor_db:
            raise ValueError("Doctor not found during booking")

        # ✅ ALWAYS create a new patient
        patient = create_patient(
            db,
            name=patient_name,
            phone=patient_phone
        )

        # ❗ Calendar creation is MANDATORY
        if DISABLE_CALENDAR:
            raise RuntimeError("Calendar integration is disabled")

        credentials = get_credentials_for_doctor(doctor_id)
        if not credentials:
            raise RuntimeError("Doctor calendar is not connected")

        service = build_calendar_service(credentials)
        tz = pytz.timezone(TIMEZONE)

        start_dt = tz.localize(
            datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        )

        if not doctor_db.avg_consult_minutes:
            raise RuntimeError("Doctor consultation duration not configured")

        end_dt = start_dt + timedelta(
            minutes=doctor_db.avg_consult_minutes
        )

        calendar_id = get_calendar_id_for_doctor(doctor_id)

        event = {
            "summary": f"New Appointment – {patient_name}",
            "description": (
                f"Patient Name: {patient_name}\n"
                f"Phone: {patient_phone}\n\n"
                f"Booked via MedSchedule AI"
            ),
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": TIMEZONE,
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": TIMEZONE,
            },
            "attendees": [
                {"email": doctor_db.email}
            ],
           "reminders": {
            "useDefault": false,
            "overrides": [
                { "method": "popup", "minutes": 30 }
            ]
        }
    }



        created = service.events().insert(
            calendarId=calendar_id,
            body=event,
            sendUpdates="all"
        ).execute()


        event_id = created["id"]

        appt = create_appointment(
            db,
            doctor_id=doctor_db.doctor_id,
            patient_id=patient.patient_id,
            appointment_date=datetime.strptime(date_str, "%Y-%m-%d").date(),
            appointment_time=datetime.strptime(time_str, "%H:%M").time(),
            status="BOOKED",
            calendar_event_id=event_id,
        )

        if not appt or not appt.calendar_event_id:
            # rollback calendar event
            service.events().delete(
                calendarId=calendar_id,
                eventId=appt.calendar_event_id,
                sendUpdates="all"
            ).execute()

            raise RuntimeError("Appointment creation failed after calendar event creation")

        db.commit()

        
        # 🔔 Doctor Notification (Safe, Non-Blocking)
        try:
            notify_doctor_via_whatsapp(
                doctor=appt.doctor,
                message=(
                    f"📅 New Appointment Booked\n\n"
                    f"Patient: {patient_name}\n"
                    f"Date: {date_str}\n"
                    f"Time: {time_str}\n"
                    f"Phone: {patient_phone}"
                )
            )
        except Exception:
            pass  # Never break booking flow

        return {
            "appointment_id": appt.appointment_id,
            "event_id": event_id,
            "date": date_str,
            "time": time_str,
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

# ------------------------------------------------------------------
# Cancel (calendar deletion now DB-first)
# ------------------------------------------------------------------
def cancel_appointment(event_id: str, doctor_id: str):
    appt = get_appointment_by_event_id(event_id)
    if not appt:
        return
    cancel_appointment_by_id(appt.appointment_id, doctor_id)




# ------------------------------------------------------------------
# Phase 6.5 – DB-first cancellation (UNCHANGED)
# ------------------------------------------------------------------
def cancel_appointment_by_id(appointment_id, doctor_id):
    appt = get_appointment_by_id(appointment_id)
    if not appt:
        return

    # 1️⃣ Delete from Google Calendar FIRST (if applicable)
    if not DISABLE_CALENDAR and appt.calendar_event_id:
        credentials = get_credentials_for_doctor(doctor_id)
        if not credentials:
            raise RuntimeError("Doctor calendar is not connected")

        calendar_id = get_calendar_id_for_doctor(doctor_id)
        service = build_calendar_service(credentials)

        try:
            service.events().delete(
                calendarId=calendar_id,
                eventId=appt.calendar_event_id,
                sendUpdates="all"
            ).execute()
        except Exception as e:
            raise RuntimeError(
                f"Failed to delete calendar event: {str(e)}"
            )

    # 2️⃣ ALWAYS cancel in DB (only if calendar delete succeeded or was not needed)
    cancel_appointment_db(appointment_id)





def is_working_day(date_str: str, doctor_id: str) -> bool:
    doctor = get_doctor_from_db(doctor_id)
    if not doctor:
        return False

    date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    weekday = date_obj.weekday()  # 0=Mon

    working_days = list(map(int, doctor.working_days.split(",")))
    return weekday in working_days


def update_calendar_event(
    *,
    doctor_id,
    event_id: str,
    new_date,
    new_time,
):
    """
    Update an existing Google Calendar event.
    Side-effect only. Must not affect DB logic.
    """
    if DISABLE_CALENDAR or not event_id:
        return

    credentials = get_credentials_for_doctor(doctor_id)
    if not credentials:
        return

    calendar_id = get_calendar_id_for_doctor(doctor_id)
    service = build_calendar_service(credentials)

    tz = pytz.timezone(TIMEZONE)
    start_dt = tz.localize(
        datetime.combine(
            datetime.strptime(new_date, "%Y-%m-%d").date(),
            datetime.strptime(new_time, "%H:%M").time(),
        )
    )
    
    doctor = get_doctor_from_db(doctor_id)
    end_dt = start_dt + timedelta(minutes=doctor.avg_consult_minutes)

    event = service.events().get(
        calendarId=calendar_id,
        eventId=event_id
    ).execute()

    event["start"] = {
        "dateTime": start_dt.isoformat(),
        "timeZone": TIMEZONE,
    }
    event["end"] = {
        "dateTime": end_dt.isoformat(),
        "timeZone": TIMEZONE,
    }

    service.events().patch(
        calendarId=calendar_id,
        eventId=event_id,
        body=event,
        sendUpdates="all"
    ).execute()





def is_within_clinic_hours(time_str: str, doctor_id) -> bool:
    db = SessionLocal()
    try:
        doctor = get_doctor_by_id(db, doctor_id)
        if not doctor:
            return False

        requested_time = datetime.strptime(time_str, "%H:%M").time()

        return doctor.work_start_time <= requested_time <= doctor.work_end_time
    finally:
        db.close()