# ═══════════════════════════════════════════════════════════════
# voice_routes.py  (v3 — follow-up agent on outbound)
# ─────────────────────────────────────────────────────────────────
# Inbound  → booking agent (run_agent via voice_agent.py)
# Outbound → post-treatment follow-up agent (follow_up_agent.py)
#
# Add ONE line to main.py:
#   from voice_routes import voice_router
#   app.include_router(voice_router)
# ═══════════════════════════════════════════════════════════════

import os
import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Response, HTTPException
from twilio.twiml.voice_response import VoiceResponse, Gather
from pydantic import BaseModel
from twilio.rest import Client as TwilioClient

from db.repository import get_doctor_by_slug
from voice_agent import process_voice_input, cleanup_call_session
from follow_up_agent import (
    create_followup_session,
    get_followup_session,
    cleanup_followup_session,
    process_followup_input,
    get_opening_message,
    is_followup_done,
)

logger = logging.getLogger("medschedule.voice")

voice_router = APIRouter(prefix="/voice", tags=["voice"])

TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
BASE_URL = os.getenv("BASE_URL", "")

VOICE = "Polly.Joanna"
LANGUAGE = "en-IN"


def _twiml_response(xml_str: str) -> Response:
    return Response(content=xml_str, media_type="application/xml")


def _gather(action_url: str, timeout: int = 6, speech_timeout: str = "auto") -> Gather:
    return Gather(
        input="speech",
        action=action_url,
        method="POST",
        timeout=timeout,
        speechTimeout=speech_timeout,
        language=LANGUAGE,
    )


# ────────────────────────────────────────────────────────────────
# 1.  INBOUND CALL — patient calls clinic
#     Configure in Twilio Console:
#       "A call comes in" → Webhook → POST
#       https://yourdomain.com/voice/inbound/dr-mukesh
# ────────────────────────────────────────────────────────────────
@voice_router.post("/inbound/{doctor_slug}")
async def voice_inbound(doctor_slug: str, request: Request):
    doctor = get_doctor_by_slug(doctor_slug)
    if not doctor:
        vr = VoiceResponse()
        vr.say("Sorry, this clinic could not be found. Goodbye.", voice=VOICE)
        vr.hangup()
        return _twiml_response(str(vr))

    form = await request.form()
    call_sid = form.get("CallSid", "unknown")
    logger.info(f"[VOICE] Inbound call | slug={doctor_slug} | sid={call_sid}")

    greeting = process_voice_input(
        call_sid=call_sid,
        speech_text="hello",
        doctor_id=str(doctor.doctor_id),
        doctor_name=doctor.name,
    )

    vr = VoiceResponse()
    gather = _gather(action_url=f"{BASE_URL}/voice/gather/{doctor_slug}")
    gather.say(greeting, voice=VOICE)
    vr.append(gather)
    vr.say("I didn't hear anything. Please call back when you are ready. Goodbye.", voice=VOICE)
    vr.hangup()
    return _twiml_response(str(vr))


# ────────────────────────────────────────────────────────────────
# 2.  INBOUND GATHER — each patient turn during booking call
# ────────────────────────────────────────────────────────────────
@voice_router.post("/gather/{doctor_slug}")
async def voice_gather(doctor_slug: str, request: Request):
    doctor = get_doctor_by_slug(doctor_slug)
    if not doctor:
        vr = VoiceResponse()
        vr.say("An error occurred. Goodbye.", voice=VOICE)
        vr.hangup()
        return _twiml_response(str(vr))

    form = await request.form()
    call_sid       = form.get("CallSid", "unknown")
    speech_result  = form.get("SpeechResult", "").strip()
    confidence_raw = form.get("Confidence", "1.0")

    try:
        conf = float(confidence_raw)
    except ValueError:
        conf = 1.0

    if conf < 0.40 or not speech_result:
        vr = VoiceResponse()
        gather = _gather(action_url=f"{BASE_URL}/voice/gather/{doctor_slug}")
        gather.say("Sorry, I didn't catch that. Could you repeat please?", voice=VOICE)
        vr.append(gather)
        vr.redirect(f"{BASE_URL}/voice/gather/{doctor_slug}", method="POST")
        return _twiml_response(str(vr))

    reply = process_voice_input(
        call_sid=call_sid,
        speech_text=speech_result,
        doctor_id=str(doctor.doctor_id),
        doctor_name=doctor.name,
    )

    vr = VoiceResponse()
    call_ending_phrases = [
        "booked", "confirmed", "cancelled", "rescheduled",
        "goodbye", "thank you", "have a great"
    ]
    is_terminal = any(p in reply.lower() for p in call_ending_phrases)

    if is_terminal:
        vr.say(reply, voice=VOICE)
        vr.pause(length=2)
        vr.say("Thank you for calling. Have a wonderful day. Goodbye!", voice=VOICE)
        vr.hangup()
    else:
        gather = _gather(action_url=f"{BASE_URL}/voice/gather/{doctor_slug}")
        gather.say(reply, voice=VOICE)
        vr.append(gather)
        vr.redirect(f"{BASE_URL}/voice/inbound/{doctor_slug}", method="POST")

    return _twiml_response(str(vr))


# ────────────────────────────────────────────────────────────────
# 3.  STATUS CALLBACK — cleans up sessions when call ends
#     Configure in Twilio Console:
#       "Call status changes" → POST https://yourdomain.com/voice/status
# ────────────────────────────────────────────────────────────────
@voice_router.post("/status")
async def voice_status(request: Request):
    form = await request.form()
    call_sid    = form.get("CallSid", "")
    call_status = form.get("CallStatus", "")

    logger.info(f"[VOICE] Status | sid={call_sid} | status={call_status}")

    if call_status in ("completed", "failed", "busy", "no-answer", "canceled"):
        cleanup_call_session(call_sid)
        cleanup_followup_session(call_sid)

    return Response(status_code=204)


# ────────────────────────────────────────────────────────────────
# 4.  OUTBOUND FOLLOW-UP TRIGGER — doctor dashboard posts here
#
#     POST /voice/followup-call
#     {
#       "to":               "+919876543210",
#       "doctor_slug":      "dr-mukesh",
#       "patient_name":     "Rahul Sharma",
#       "treatment_key":    "root_canal",
#       "treatment_display":"Root Canal Treatment",
#       "appointment_date": "2025-04-02"
#     }
# ────────────────────────────────────────────────────────────────
class FollowUpCallRequest(BaseModel):
    to:                str
    doctor_slug:       str
    patient_name:      str
    treatment_key:     str
    treatment_display: str
    appointment_date:  str


@voice_router.post("/followup-call")
async def trigger_followup_call(payload: FollowUpCallRequest, request: Request):
    """
    Initiates an outbound AI follow-up call to a patient.
    The follow-up agent conducts a full two-way post-treatment
    check-in conversation — pain, medication, swelling, diet, concerns.
    """
    from main import require_doctor
    try:
        doctor_id = require_doctor(request)
    except HTTPException:
        raise HTTPException(status_code=401, detail="Not authenticated")

    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token  = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = TWILIO_PHONE_NUMBER

    if not account_sid or not auth_token or not from_number:
        raise HTTPException(status_code=500, detail="Twilio credentials not configured.")

    doctor = get_doctor_by_slug(payload.doctor_slug)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    params = urlencode({
        "patient_name":      payload.patient_name,
        "treatment_key":     payload.treatment_key,
        "treatment_display": payload.treatment_display,
        "appointment_date":  payload.appointment_date,
        "doctor_id":         str(doctor.doctor_id),
    })
    outbound_url = f"{BASE_URL}/voice/followup-answer/{payload.doctor_slug}?{params}"

    client = TwilioClient(account_sid, auth_token)
    try:
        call = client.calls.create(
            to=payload.to,
            from_=from_number,
            url=outbound_url,
            method="POST",
            status_callback=f"{BASE_URL}/voice/status",
            status_callback_method="POST",
        )
        logger.info(
            f"[VOICE] Follow-up call initiated | sid={call.sid} | "
            f"to={payload.to} | patient={payload.patient_name} | "
            f"treatment={payload.treatment_key}"
        )
        return {"status": "initiated", "call_sid": call.sid}

    except Exception as e:
        logger.error(f"[VOICE] Follow-up call failed: {e}")
        raise HTTPException(status_code=502, detail=f"Call failed: {str(e)}")


# ────────────────────────────────────────────────────────────────
# 5.  OUTBOUND ANSWERED — patient picks up
# ────────────────────────────────────────────────────────────────
@voice_router.post("/followup-answer/{doctor_slug}")
async def voice_followup_answered(doctor_slug: str, request: Request):
    """
    Patient picked up. Creates the follow-up session,
    speaks the opening message, opens the gather loop.
    """
    doctor = get_doctor_by_slug(doctor_slug)
    if not doctor:
        vr = VoiceResponse()
        vr.say("Sorry, there was an error. Goodbye.", voice=VOICE)
        vr.hangup()
        return _twiml_response(str(vr))

    form   = await request.form()
    params = request.query_params

    call_sid          = form.get("CallSid", "unknown")
    patient_name      = params.get("patient_name", "there")
    treatment_key     = params.get("treatment_key", "dental_checkup")
    treatment_display = params.get("treatment_display", "dental procedure")
    appointment_date  = params.get("appointment_date", "recently")
    doctor_id         = params.get("doctor_id", str(doctor.doctor_id))

    logger.info(
        f"[VOICE] Follow-up answered | sid={call_sid} | "
        f"patient={patient_name} | treatment={treatment_key}"
    )

    state = create_followup_session(
        call_sid=call_sid,
        doctor_id=doctor_id,
        doctor_name=doctor.name,
        patient_name=patient_name,
        treatment_key=treatment_key,
        treatment_display=treatment_display,
        appointment_date=appointment_date,
    )

    opening = get_opening_message(state)

    vr = VoiceResponse()
    gather = _gather(
        action_url=f"{BASE_URL}/voice/followup-gather/{doctor_slug}",
        timeout=8,
    )
    gather.say(opening, voice=VOICE)
    vr.append(gather)
    vr.say("I didn't hear a response. We will try again later. Goodbye.", voice=VOICE)
    vr.hangup()
    return _twiml_response(str(vr))


# ────────────────────────────────────────────────────────────────
# 6.  FOLLOW-UP GATHER — each patient turn during follow-up call
# ────────────────────────────────────────────────────────────────
@voice_router.post("/followup-gather/{doctor_slug}")
async def voice_followup_gather(doctor_slug: str, request: Request):
    """
    Receives patient speech during a follow-up call.
    Runs through the follow-up agent and continues the conversation.
    """
    form = await request.form()
    call_sid       = form.get("CallSid", "unknown")
    speech_result  = form.get("SpeechResult", "").strip()
    confidence_raw = form.get("Confidence", "1.0")

    try:
        conf = float(confidence_raw)
    except ValueError:
        conf = 1.0

    vr = VoiceResponse()

    if conf < 0.35 or not speech_result:
        gather = _gather(
            action_url=f"{BASE_URL}/voice/followup-gather/{doctor_slug}",
            timeout=8,
        )
        gather.say("Sorry, I didn't quite catch that. Could you say that again please?", voice=VOICE)
        vr.append(gather)
        return _twiml_response(str(vr))

    reply = process_followup_input(call_sid=call_sid, speech_text=speech_result)

    if not reply or is_followup_done(call_sid):
        vr.say(
            "Thank you so much for your time. We hope you are feeling better soon. "
            "If you need anything, please do not hesitate to call the clinic. Goodbye!",
            voice=VOICE,
        )
        vr.hangup()
        return _twiml_response(str(vr))

    ending_phrases = ["goodbye", "take care", "feel better soon", "call the clinic directly"]
    is_terminal = any(p in reply.lower() for p in ending_phrases)

    if is_terminal:
        vr.say(reply, voice=VOICE)
        vr.pause(length=1)
        vr.hangup()
    else:
        gather = _gather(
            action_url=f"{BASE_URL}/voice/followup-gather/{doctor_slug}",
            timeout=8,
        )
        gather.say(reply, voice=VOICE)
        vr.append(gather)
        vr.say("Are you still there? Take your time.", voice=VOICE)
        vr.redirect(f"{BASE_URL}/voice/followup-gather/{doctor_slug}", method="POST")

    return _twiml_response(str(vr))