from datetime import datetime, timedelta
from calendar_oauth import build_calendar_service
from auth_store import oauth_store
from doctor_config import DOCTOR_CONFIG
import pytz

TIMEZONE = "Asia/Kolkata"


def check_availability(date_str: str, time_str: str) -> bool:
    print("CHECKING AVAILABILITY:", date_str, time_str)

    credentials = oauth_store.get("credentials")
    if not credentials:
        raise RuntimeError("Calendar not connected")

    service = build_calendar_service(credentials)
    tz = pytz.timezone(TIMEZONE)

    start_dt = tz.localize(
        datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    )

    duration = DOCTOR_CONFIG["slot_duration_minutes"]
    buffer_minutes = DOCTOR_CONFIG["buffer_minutes"]
    end_dt = start_dt + timedelta(minutes=duration)

    # ❌ Working day check
    if start_dt.weekday() not in DOCTOR_CONFIG["working_days"]:
        print("⛔ Not a working day")
        return False

    # ❌ Working hours check
    wh_start = DOCTOR_CONFIG["working_hours"]["start"]
    wh_end = DOCTOR_CONFIG["working_hours"]["end"]

    if not (wh_start <= start_dt.time() and end_dt.time() <= wh_end):
        print("⛔ Outside working hours")
        return False

    # ✅ Calendar overlap (UTC-safe)
    events_result = service.events().list(
        calendarId="primary",
        timeMin=(start_dt - timedelta(minutes=buffer_minutes))
        .astimezone(pytz.UTC)
        .isoformat(),
        timeMax=(end_dt + timedelta(minutes=buffer_minutes))
        .astimezone(pytz.UTC)
        .isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    if events_result.get("items"):
        print("⛔ Slot busy")
        return False

    return True


def book_appointment(
    date_str: str,
    time_str: str,
    patient_name: str,
    patient_phone: str,
) -> dict:
    credentials = oauth_store.get("credentials")
    if not credentials:
        raise RuntimeError("Calendar not connected")

    service = build_calendar_service(credentials)
    tz = pytz.timezone(TIMEZONE)

    start_dt = tz.localize(
        datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    )

    duration = DOCTOR_CONFIG["slot_duration_minutes"]
    end_dt = start_dt + timedelta(minutes=duration)

    event = {
        "summary": f"Patient Appointment – {patient_name}",
        "description": (
            f"Patient Name: {patient_name}\n"
            f"Phone: {patient_phone}\n"
            f"Booked via AI Appointment Agent"
        ),
        "start": {"dateTime": start_dt.isoformat(), "timeZone": TIMEZONE},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": TIMEZONE},
    }

    created_event = service.events().insert(
        calendarId="primary", body=event
    ).execute()

    return {
        "status": "BOOKED",
        "event_id": created_event.get("id"),
        "date": date_str,
        "time": time_str,
        "calendar_link": created_event.get("htmlLink"),
    }
