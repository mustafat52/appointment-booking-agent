from datetime import datetime, timedelta
import pytz

from calendar_oauth import build_calendar_service
from auth_store import oauth_store
from doctor_config import DOCTORS, DEFAULT_DOCTOR_ID

TIMEZONE = "Asia/Kolkata"


def _get_doctor(doctor_id: str):
    doctor = DOCTORS.get(doctor_id)
    if not doctor:
        doctor = DOCTORS[DEFAULT_DOCTOR_ID]
    return doctor


def check_availability(date_str: str, time_str: str, doctor_id: str) -> bool:
    print("CHECKING AVAILABILITY:", date_str, time_str, doctor_id)

    credentials = oauth_store.get("credentials")
    if not credentials:
        raise RuntimeError("Calendar not connected")

    doctor = _get_doctor(doctor_id)

    service = build_calendar_service(credentials)
    tz = pytz.timezone(TIMEZONE)

    start_dt = tz.localize(
        datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    )

    duration = doctor["slot_duration_minutes"]
    buffer_minutes = doctor["buffer_minutes"]
    end_dt = start_dt + timedelta(minutes=duration)

    # ❌ Working day check
    if start_dt.weekday() not in doctor["working_days"]:
        return False

    # ❌ Working hours check
    wh_start = datetime.strptime(
        doctor["working_hours"]["start"], "%H:%M"
    ).time()
    wh_end = datetime.strptime(
        doctor["working_hours"]["end"], "%H:%M"
    ).time()

    if not (wh_start <= start_dt.time() and end_dt.time() <= wh_end):
        return False

    # ✅ Calendar overlap
    events = service.events().list(
        calendarId=doctor["calendar_id"],
        timeMin=(start_dt - timedelta(minutes=buffer_minutes))
        .astimezone(pytz.UTC)
        .isoformat(),
        timeMax=(end_dt + timedelta(minutes=buffer_minutes))
        .astimezone(pytz.UTC)
        .isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    return not events.get("items")


def book_appointment(
    date_str: str,
    time_str: str,
    doctor_id: str,
    patient_name: str,
    patient_phone: str,
) -> dict:
    credentials = oauth_store.get("credentials")
    if not credentials:
        raise RuntimeError("Calendar not connected")

    doctor = _get_doctor(doctor_id)

    service = build_calendar_service(credentials)
    tz = pytz.timezone(TIMEZONE)

    start_dt = tz.localize(
        datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    )

    end_dt = start_dt + timedelta(
        minutes=doctor["slot_duration_minutes"]
    )

    event = {
        "summary": f"Patient Appointment – {patient_name}",
        "description": (
            f"Doctor: {doctor['name']}\n"
            f"Patient Name: {patient_name}\n"
            f"Phone: {patient_phone}\n"
            f"Booked via AI Appointment Agent"
        ),
        "start": {"dateTime": start_dt.isoformat(), "timeZone": TIMEZONE},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": TIMEZONE},
    }

    created_event = service.events().insert(
        calendarId=doctor["calendar_id"],
        body=event
    ).execute()

    return {
        "status": "BOOKED",
        "event_id": created_event.get("id"),
        "date": date_str,
        "time": time_str,
        "calendar_link": created_event.get("htmlLink"),
    }
