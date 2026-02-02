import os
from pydoc import html
import re
import pytz
from typing import Dict
from datetime import time
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse,HTMLResponse
from pydantic import BaseModel, EmailStr
import uuid
from schema import ChatRequest, ChatResponse, DoctorRescheduleRequest
from agent import run_agent
from state import BookingState

from calendar_oauth import get_oauth_flow , build_calendar_service
from auth_store import oauth_store

from doctor_config import DOCTORS

from db.repository import (create_doctor, doctor_exists, get_doctor_by_slug,get_doctor_by_email, 
                           get_upcoming_appointments_for_doctor,
                           get_appointment_by_id, cancel_appointment_db , reschedule_appointment_db,
                           get_todays_appointments_for_doctor)


from tools import cancel_appointment, check_availability
from email_service import send_daily_appointments_email


app = FastAPI()

TIMEZONE = "Asia/Kolkata"

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")


# 🏠 Homepage route
@app.get("/")
def serve_homepage():
    """Professional landing page"""
    return FileResponse("static/homepage.html")


# session_id -> BookingState
state_store: Dict[str, BookingState] = {}


# -------------------------------
# Doctor resolution helper
# -------------------------------
from db.repository import get_doctor_by_slug
from doctor_config import DOCTORS

 
 
def normalize_slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug



def resolve_doctor_or_404(doctor_slug: str):
    # 1️⃣ DB-first lookup
    doctor = get_doctor_by_slug(doctor_slug)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    if doctor:
        return {
            "id": doctor.doctor_id,
            "slug": doctor.slug,
            "name": doctor.name,
            "email": doctor.email,
            "calendar_id": doctor.calendar_id,
            "working_days": doctor.working_days,
            "work_start_time": doctor.work_start_time,
            "work_end_time": doctor.work_end_time,
            "avg_consult_minutes": doctor.avg_consult_minutes,
            "buffer_minutes": doctor.buffer_minutes,
        }

    # 2️⃣ Config fallback
    config_doctor = DOCTORS.get(doctor_slug)
    if config_doctor:
        return config_doctor

    # 3️⃣ Hard fail
    raise HTTPException(status_code=404, detail="Doctor not found")



# -------------------------------
# Doctor-specific booking URL
# -------------------------------

@app.get("/book/{doctor_slug}")
def serve_doctor_ui(doctor_slug: str, request: Request):
    doctor = resolve_doctor_or_404(doctor_slug)

    session_id = request.cookies.get("session_id")

    if not session_id:
        session_id = str(uuid.uuid4())

    if session_id not in state_store:
        state_store[session_id] = BookingState()

    state = state_store[session_id]

    state.reset_flow()
    state.doctor_id = doctor["id"]
    state.doctor_name = doctor["name"]
    state.greeted = False

    with open("static/index.html", "r", encoding="utf-8") as f:
        html = f.read()

    html = html.replace("{{DOCTOR_SLUG}}", doctor_slug)

    response = HTMLResponse(html)

    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True
    )

    return response


# -------------------------------
# Chat endpoint
# -------------------------------
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request):
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(
            status_code=400,
            detail="Session missing. Please start booking from the doctor's page."
        )


    if session_id not in state_store:
        state_store[session_id] = BookingState()

    state = state_store[session_id]

    if not state.doctor_id:
        raise HTTPException(
            status_code=400,
            detail="Doctor context is missing. Please start booking via the doctor's booking link."
        )

    try:
        reply = run_agent(req.message, state)
        
    except Exception as e:
        state.reset_flow()
        reply = (
        "⚠️ Something went wrong on our side.\n"
        "Let's start fresh. How can I help you?"
    )
        
    return ChatResponse(reply=reply)




# -------------------------------
# OAuth – connect calendar
# -------------------------------
@app.get("/connect-calendar/{doctor_slug}")
def connect_calendar(doctor_slug: str):
    doctor = get_doctor_by_slug(doctor_slug)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    flow = get_oauth_flow()

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    oauth_store["flow"] = flow
    oauth_store["pending_doctor"] = str(doctor.doctor_id)

    return RedirectResponse(auth_url)



# -------------------------------
# OAuth callback
# -------------------------------
@app.get("/oauth/callback")
def oauth_callback(request: Request):
    flow = oauth_store.get("flow")
    if not flow:
        raise HTTPException(
            status_code=400,
            detail="OAuth flow missing. Please reconnect calendar."
        )

    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    if not redirect_uri:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_REDIRECT_URI not set"
        )

    auth_response = f"{redirect_uri}?{request.query_params}"

    try:
        flow.fetch_token(authorization_response=auth_response)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"OAuth failed: {str(e)}"
        )

    doctor_id = oauth_store.get("pending_doctor")
    if not doctor_id:
        raise HTTPException(
            status_code=400,
            detail="Doctor context missing during OAuth"
        )

    credentials = flow.credentials

    service = build_calendar_service(credentials)

    calendar_list = service.calendarList().list().execute()
    primary_calendar = None

    for cal in calendar_list.get("items", []):
        if cal.get("primary"):
            primary_calendar = cal
            break

    if not primary_calendar:
        raise HTTPException(
            status_code=400,
            detail="No primary calendar found for this account"
        )

    from datetime import datetime, timedelta
    from db.repository import save_doctor_calendar_credentials

    expires_at = credentials.expiry
    if not expires_at:
        expires_at = datetime.utcnow() + timedelta(hours=1)

    save_doctor_calendar_credentials(
        doctor_id=doctor_id,
        provider="google",
        calendar_id=primary_calendar["id"],
        access_token=credentials.token,
        refresh_token=credentials.refresh_token,
        expires_at=expires_at,
    )

    oauth_store["credentials"][doctor_id] = credentials

    oauth_store["pending_doctor"] = None
    oauth_store["flow"] = None

    return {"status": "Calendar connected successfully 🎉"}



# -------------------------------
# Doctor onboarding
# -------------------------------
class DoctorOnboardRequest(BaseModel):
    name: str
    email: EmailStr
    clinic_email: EmailStr
    whatsapp_number: str
    slug: str | None = None
    working_days: list[int]
    work_start_time: time
    work_end_time: time
    avg_consult_minutes: int
    buffer_minutes: int


@app.get("/doctors/onboard")
def serve_doctor_onboard_ui():
    return FileResponse("static/doc_onboard.html")


@app.post("/doctors/onboard", status_code=201)
def onboard_doctor(payload: DoctorOnboardRequest):
    if payload.work_start_time >= payload.work_end_time:
        raise HTTPException(
            status_code=400,
            detail="work_start_time must be before work_end_time"
        )

    slug = payload.slug or normalize_slug(payload.name)

    if get_doctor_by_slug(slug):
        raise HTTPException(
            status_code=400,
            detail=f"Doctor slug '{slug}' already exists"
        )
    
    if get_doctor_by_email(payload.email):
        raise HTTPException(
        status_code=400,
        detail=f"Doctor with email '{payload.email}' already exists"
    )


    doctor = create_doctor(
        name=payload.name,
        email=payload.email,
        clinic_email=payload.clinic_email,
        whatsapp_number=payload.whatsapp_number,
        slug=slug,
        working_days=payload.working_days,
        work_start_time=payload.work_start_time,
        work_end_time=payload.work_end_time,
        avg_consult_minutes=payload.avg_consult_minutes,
        buffer_minutes=payload.buffer_minutes,
    )

    return {
    "doctor_id": str(doctor.doctor_id),
    "slug": doctor.slug,
    "connect_calendar_url": f"/connect-calendar/{doctor.slug}",
    "message": "Doctor onboarded successfully"
    }





@app.get("/doctor/{doctor_id}/appointments")
def list_doctor_appointments(
    doctor_id: str,
    limit: int = 50
):
    appointments = get_upcoming_appointments_for_doctor(
        doctor_id=doctor_id,
        limit=limit
    )

    return [
        {
            "appointment_id": str(a.appointment_id),
            "patient_name": a.patient.name,
            "patient_phone": a.patient.phone,
            "date": a.appointment_date.isoformat(),
            "time": a.appointment_time.strftime("%H:%M"),
            "status": a.status,
        }
        for a in appointments
    ]




@app.post("/doctor/{doctor_id}/appointments/{appointment_id}/cancel")
def doctor_cancel_appointment(
    doctor_id: str,
    appointment_id: str
):
    appt = get_appointment_by_id(appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if str(appt.doctor_id) != doctor_id:
        raise HTTPException(
            status_code=403,
            detail="Cannot cancel another doctor's appointment"
        )

    cancel_appointment_db(appointment_id)

    if appt.calendar_event_id:
        cancel_appointment(
            event_id=appt.calendar_event_id,
            doctor_id=doctor_id
        )

    return {"status": "Appointment cancelled successfully"}



@app.post("/doctor/{doctor_id}/appointments/{appointment_id}/reschedule")
def doctor_reschedule_appointment(
    doctor_id: str,
    appointment_id: str,
    payload: DoctorRescheduleRequest
):
    appt = get_appointment_by_id(appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if str(appt.doctor_id) != doctor_id:
        raise HTTPException(
            status_code=403,
            detail="Cannot reschedule another doctor's appointment"
        )

    date_str = payload.new_date.isoformat()
    time_str = payload.new_time.strftime("%H:%M")

    if not check_availability(date_str, time_str, doctor_id):
        raise HTTPException(
            status_code=400,
            detail="Selected slot is not available"
        )

    reschedule_appointment_db(
        appointment_id=appointment_id,
        new_date=payload.new_date,
        new_time=payload.new_time,
        new_calendar_event_id=appt.calendar_event_id
    )

    if appt.calendar_event_id:
        from tools import get_credentials_for_doctor, get_calendar_id_for_doctor
        credentials = get_credentials_for_doctor(doctor_id)

        if credentials:
            service = build_calendar_service(credentials)
            tz = pytz.timezone(TIMEZONE)

            start_dt = tz.localize(
                datetime.combine(payload.new_date, payload.new_time)
            )

            end_dt = start_dt + timedelta(minutes=appt.doctor.avg_consult_minutes)

            service.events().patch(
                calendarId=get_calendar_id_for_doctor(doctor_id),
                eventId=appt.calendar_event_id,
                body={
                    "start": {
                        "dateTime": start_dt.isoformat(),
                        "timeZone": TIMEZONE
                    },
                    "end": {
                        "dateTime": end_dt.isoformat(),
                        "timeZone": TIMEZONE
                    },
                }
            ).execute()

    return {"status": "Appointment rescheduled successfully"}



@app.post("/internal/send-daily-emails")
def send_daily_emails():
    from db.database import SessionLocal
    from db.models import Doctor

    db = SessionLocal()
    doctors = db.query(Doctor).filter(Doctor.is_active == True).all()

    for d in doctors:
        if not d.clinic_email:
            continue

        appointments = get_todays_appointments_for_doctor(d.doctor_id)
        send_daily_appointments_email(
            clinic_email=d.clinic_email,
            doctor_name=d.name,
            appointments=appointments
        )

    return {"status": "Emails processed"}