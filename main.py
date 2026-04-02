import os
from pydoc import html
import re
import pytz
import qrcode
import io
import base64

from typing import Dict
from datetime import time
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse, Response, JSONResponse
from pydantic import BaseModel, EmailStr
import uuid
from schema import ChatRequest, ChatResponse, DoctorRescheduleRequest
from agent import run_agent
from state import BookingState
from channel.web import init_session, handle_web_message
from channel.whatsapp import handle_whatsapp_message, whatsapp_state_store
from calendar_oauth import get_oauth_flow, build_calendar_service
from auth_store import oauth_store
from twilio.twiml.messaging_response import MessagingResponse
from doctor_config import DOCTORS
from db.database import SessionLocal
from db.repository import (create_doctor, doctor_exists, get_doctor_by_slug, get_doctor_by_email,
                           get_upcoming_appointments_for_doctor,
                           get_appointment_by_id, cancel_appointment_db, reschedule_appointment_db,
                           get_todays_appointments_for_doctor, get_doctor_auth_by_email, update_doctor_last_login, get_doctor_by_id,
                           get_doctor_auth_by_doctor_id, create_doctor_auth)

from tools import cancel_appointment_by_id, check_availability, update_calendar_event
from email_service import send_daily_appointments_email
from auth_utils import hash_password, verify_password

# ── FIX: moved here from line ~1030 so /ask-dentist can use it ──
from services.dental_ai_service import get_dental_ai_response
from fastapi import File, Form, UploadFile

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("medschedule")


app = FastAPI()

from voice_routes import voice_router
app.include_router(voice_router)

from call_log_route import call_log_router   # optional, for dashboard
app.include_router(call_log_router)

doctor_sessions = {}

TIMEZONE = "Asia/Kolkata"


def normalize_phone(number: str) -> str:
    number = number.strip()
    number = re.sub(r"[^\d+]", "", number)

    if number.startswith("00"):
        number = "+" + number[2:]

    if not number.startswith("+"):
        number = "+91" + number

    return number


def require_doctor(request: Request):
    session_id = request.cookies.get("doctor_session")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    doctor_id = doctor_sessions.get(session_id)
    if not doctor_id:
        raise HTTPException(status_code=401, detail="Invalid session")

    return doctor_id

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_IMAGE_SIZE_BYTES = 4 * 1024 * 1024  # 4 MB


class DentalKnowledgeRequest(BaseModel):
    message: str


# ── Route ────────────────────────────────────────────────────────
@app.post("/ask-dentist")
async def ask_dentist(payload: DentalKnowledgeRequest):
    """
    Public dental knowledge chatbot — text only, JSON body.
    Answers patient questions about symptoms, treatments, and care.
    Reuses get_dental_ai_response() — same Groq service as /dental-chat.
    No session cookie required. Separate from /chat booking bot.
    """
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    reply = await get_dental_ai_response(user_message=payload.message)
    return JSONResponse({"reply": reply})


# 🏠 Homepage route
@app.get("/")
def serve_homepage():
    """Professional landing page"""
    return FileResponse("static/homepage.html")


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

    init_session(
        session_id=session_id,
        doctor_id=doctor["id"],
        doctor_name=doctor["name"]
    )

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

    reply = handle_web_message(
        session_id=session_id,
        user_message=req.message
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

    # 🔐 Decide next step based on DoctorAuth existence
    auth = get_doctor_auth_by_doctor_id(doctor_id)

    if auth:
        # Doctor already has login credentials
        return RedirectResponse(
            url="/static/doc_login.html",
            status_code=302
        )

    # First-time doctor → force password setup
    return RedirectResponse(
        url=f"/static/doc_signup.html?doctor_id={doctor_id}",
        status_code=302
    )


# -------------------------------
# Doctor onboarding
# -------------------------------
class DoctorOnboardRequest(BaseModel):
    name: str
    email: EmailStr
    clinic_email: EmailStr
    doctor_whatsapp_number: str
    clinic_phone_number: str
    slug: str | None = None
    working_days: list[int]
    work_start_time: time
    work_end_time: time
    avg_consult_minutes: int
    buffer_minutes: int


class DoctorSignupRequest(BaseModel):
    doctor_id: str
    password: str


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

    doctor_whatsapp = normalize_phone(payload.doctor_whatsapp_number)
    clinic_phone = normalize_phone(payload.clinic_phone_number)

    doctor = create_doctor(
        name=payload.name,
        email=payload.email,
        clinic_email=payload.clinic_email,
        doctor_whatsapp_number=doctor_whatsapp,
        clinic_phone_number=clinic_phone,
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
    raise HTTPException(
        status_code=410,
        detail="This endpoint is deprecated. Use doctor dashboard APIs."
    )


@app.post("/doctor/{doctor_id}/appointments/{appointment_id}/reschedule")
def doctor_reschedule_appointment(
    doctor_id: str,
    appointment_id: str,
    payload: DoctorRescheduleRequest
):
    raise HTTPException(
        status_code=410,
        detail="This endpoint is deprecated. Use doctor dashboard APIs."
    )


@app.post("/auth/doctor/login")
def doctor_login(payload: dict, request: Request, response: Response):
    from auth_utils import verify_password
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")

    auth = get_doctor_auth_by_email(email)
    if not auth or not verify_password(password, auth.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    update_doctor_last_login(auth.id)

    session_id = str(uuid.uuid4())
    doctor_sessions[session_id] = str(auth.doctor_id)

    resp = JSONResponse({"status": "ok"})
    resp.set_cookie(
        key="doctor_session",
        value=session_id,
        httponly=True,
        samesite="lax",
    )
    return resp


@app.post("/auth/doctor/logout")
def doctor_logout(request: Request, response: Response):
    session_id = request.cookies.get("doctor_session")
    if session_id and session_id in doctor_sessions:
        del doctor_sessions[session_id]
    resp = JSONResponse({"status": "logged_out"})
    resp.delete_cookie("doctor_session")
    return resp


@app.get("/api/doctor/me")
def get_doctor_me(request: Request):
    doctor_id = require_doctor(request)
    db = SessionLocal()
    try:
        doctor = get_doctor_by_id(db, doctor_id)
    finally:
        db.close()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return {
        "doctor_id": str(doctor.doctor_id),
        "name": doctor.name,
        "email": doctor.email,
        "slug": doctor.slug,
        "working_days": doctor.working_days,
        "work_start_time": str(doctor.work_start_time),
        "work_end_time": str(doctor.work_end_time),
        "avg_consult_minutes": doctor.avg_consult_minutes,
    }


@app.get("/api/doctor/appointments/today")
def get_todays_appointments(request: Request):
    doctor_id = require_doctor(request)
    appointments = get_todays_appointments_for_doctor(doctor_id)
    return [
        {
            "appointment_id": str(a.appointment_id),
            "date": a.appointment_date.isoformat(),
            "time": a.appointment_time.strftime("%H:%M"),
            "status": a.status,
            "patient_name": a.patient.name if a.patient else None,
            "patient_phone": a.patient.phone if a.patient else None,
        }
        for a in appointments
    ]


@app.get("/api/doctor/appointments/upcoming")
def get_upcoming_appointments(request: Request, limit: int = 50):
    doctor_id = require_doctor(request)
    appointments = get_upcoming_appointments_for_doctor(doctor_id, limit=limit)
    return [
        {
            "appointment_id": str(a.appointment_id),
            "date": a.appointment_date.isoformat(),
            "time": a.appointment_time.strftime("%H:%M"),
            "status": a.status,
            "patient_name": a.patient.name if a.patient else None,
            "patient_phone": a.patient.phone if a.patient else None,
        }
        for a in appointments
    ]


@app.post("/auth/doctor/signup")
def doctor_signup(payload: DoctorSignupRequest):
    # 1️⃣ Validate doctor exists
    db = SessionLocal()
    try:
        doctor = get_doctor_by_id(db, payload.doctor_id)
    finally:
        db.close()

    if not doctor:
        raise HTTPException(
            status_code=400,
            detail="Invalid signup request"
        )

    # 2️⃣ Prevent duplicate signup
    existing = get_doctor_auth_by_doctor_id(payload.doctor_id)
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Account already created. Please log in."
        )

    # 3️⃣ Hash password
    password_hash = hash_password(payload.password)

    # 4️⃣ Create DoctorAuth
    create_doctor_auth(
        doctor_id=doctor.doctor_id,
        email=doctor.email,
        password_hash=password_hash
    )

    return {"status": "account_created"}


from fastapi import BackgroundTasks


@app.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.form()

        from_number = payload.get("From")
        to_number = payload.get("To")
        body = payload.get("Body", "").strip()

        logger.info(
            f"Incoming message | from={from_number} | to={to_number} | body='{body}'"
        )

        background_tasks.add_task(
            process_whatsapp_message,
            from_number,
            to_number,
            body
        )

    except Exception as e:
        logger.exception("Webhook error occurred")

    return Response(status_code=200)


def generate_whatsapp_qr(platform_number: str, doctor_id: str):
    clean_number = platform_number.replace("+", "").replace(" ", "")

    entry_text = f"START_{doctor_id}"
    wa_link = f"https://wa.me/{clean_number}?text={entry_text}"

    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=4,
    )

    qr.add_data(wa_link)
    qr.make(fit=True)

    img = qr.make_image(fill="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_base64 = base64.b64encode(buffer.getvalue()).decode()

    return {
        "wa_link": wa_link,
        "qr_base64": img_base64
    }


@app.get("/api/doctor/whatsapp-qr")
def get_doctor_whatsapp_qr(request: Request):
    session_id = request.cookies.get("doctor_session")
    doctor_id = doctor_sessions.get(session_id)

    if not doctor_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    db = SessionLocal()
    try:
        doctor = get_doctor_by_id(db, doctor_id)
    finally:
        db.close()

    if not doctor:
        raise HTTPException(
            status_code=400,
            detail="Doctor not found."
        )

    PLATFORM_WHATSAPP_NUMBER = "+14155238886"

    return generate_whatsapp_qr(
        PLATFORM_WHATSAPP_NUMBER,
        doctor.doctor_id
    )


import time as time_module

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")

from twilio.rest import Client
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


@app.get("/test-whatsapp")
def test_whatsapp():
    try:
        message = twilio_client.messages.create(
            body="✅ REST WhatsApp test successful!",
            from_=TWILIO_WHATSAPP_NUMBER,
            to="whatsapp:+919550253852"
        )
        return {"status": "sent", "sid": message.sid}
    except Exception as e:
        return {"error": str(e)}


def process_whatsapp_message(from_number, to_number, body):
    start_time = time_module.time()

    try:
        logger.info(
            f"Processing started | from={from_number} | body='{body}'"
        )

        reply_text = handle_whatsapp_message(
            from_number=from_number,
            to_number=to_number,
            message_body=body
        )

        duration = round(time_module.time() - start_time, 3)

        logger.info(
            f"Reply generated | from={from_number} | duration={duration}s"
        )

        twilio_client.messages.create(
            body=reply_text,
            from_=f"whatsapp:{TWILIO_WHATSAPP_NUMBER}",
            to=from_number,
        )

        logger.info(
            f"Reply sent successfully | to={from_number}"
        )

    except Exception:
        logger.exception(
            f"Processing error | from={from_number}"
        )

        try:
            twilio_client.messages.create(
                body="⚠️ Sorry, something went wrong.\nPlease type 0 to restart.",
                from_=TWILIO_WHATSAPP_NUMBER,
                to=from_number,
            )
            logger.info(
                f"Fallback message sent | to={from_number}"
            )
        except Exception:
            logger.exception(
                f"Fallback send failed | to={from_number}"
            )


# -----------------------------------------------
# Dental AI Triage Chat  (homepage floating bot)
# Supports text-only AND image + text queries.
# -----------------------------------------------
@app.post("/dental-chat")
async def dental_chat(
    message: str = Form(default=""),
    image: UploadFile | None = File(default=None),
):
    """
    Public AI dental triage endpoint.
    Accepts multipart/form-data with:
      - message  (str, optional if image is sent)
      - image    (file, optional — jpg/png/webp/gif, max 4 MB)
    """
    if not message.strip() and image is None:
        raise HTTPException(status_code=400, detail="Please provide a message or an image.")

    image_bytes = None
    image_content_type = "image/jpeg"

    if image is not None:
        if image.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported image type: {image.content_type}. Please upload JPG, PNG, or WebP."
            )

        image_bytes = await image.read()

        if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Image is too large. Please upload an image under 4 MB."
            )

        image_content_type = image.content_type
        logger.info(
            f"Dental chat image received | type={image.content_type} | size={len(image_bytes)} bytes"
        )

    reply = await get_dental_ai_response(
        user_message=message,
        image_bytes=image_bytes,
        image_content_type=image_content_type,
    )

    return JSONResponse({"reply": reply})