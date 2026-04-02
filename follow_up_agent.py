# follow_up_agent.py
# ─────────────────────────────────────────────────────────────────
# Autonomous post-treatment follow-up voice agent.
#
# Purpose: After a patient has a dental procedure, the clinic
# triggers an outbound call. This agent conducts the full
# follow-up conversation — pain check, medication adherence,
# recovery status — and logs a structured summary.
#
# Completely separate from the booking agent (run_agent).
# Uses Groq directly for intelligent, contextual conversation.
# ─────────────────────────────────────────────────────────────────

import os
import json
import logging
import re
import httpx
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional

logger = logging.getLogger("medschedule.followup")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME   = os.getenv("MODEL_NAME", "llama-3.3-70b-versatile")


# ─────────────────────────────────────────────────────────────────
# Follow-up session state
# ─────────────────────────────────────────────────────────────────

class FollowUpStage(Enum):
    GREETING        = auto()   # Introduce call, confirm identity
    PAIN_CHECK      = auto()   # Is the patient experiencing pain?
    PAIN_DETAILS    = auto()   # If yes — where, how severe, type
    MEDICATION      = auto()   # Are they taking prescribed meds?
    MEDICATION_ISSUE= auto()   # If no — why, what's the barrier
    SWELLING        = auto()   # Any swelling or bleeding?
    EATING          = auto()   # Can they eat / diet compliance
    OPEN_CONCERNS   = auto()   # Anything else on their mind
    CLOSE           = auto()   # Wrap up, advise follow-up if needed
    DONE            = auto()   # Call complete


@dataclass
class FollowUpState:
    call_sid: str
    doctor_id: str
    doctor_name: str
    patient_name: str
    treatment_key: str          # e.g. "root_canal"
    treatment_display: str      # e.g. "Root Canal Treatment"
    appointment_date: str       # ISO date string e.g. "2025-04-02"

    stage: FollowUpStage = FollowUpStage.GREETING

    # Collected data
    pain_reported: Optional[bool]   = None
    pain_severity: Optional[str]    = None   # "mild" | "moderate" | "severe"
    pain_location: Optional[str]    = None
    pain_type: Optional[str]        = None   # "throbbing" | "sharp" | "dull" etc.
    taking_medication: Optional[bool] = None
    medication_issue: Optional[str] = None
    swelling_reported: Optional[bool] = None
    eating_normally: Optional[bool] = None
    open_concerns: Optional[str]    = None
    needs_urgent_attention: bool    = False

    # Full conversation history for Groq context
    history: list[dict] = field(default_factory=list)

    # Turn counter (safety — end call if too long)
    turn_count: int = 0
    MAX_TURNS:  int = 20


# ─────────────────────────────────────────────────────────────────
# In-memory session store  (call_sid → FollowUpState)
# ─────────────────────────────────────────────────────────────────
followup_sessions: dict[str, FollowUpState] = {}


def create_followup_session(
    call_sid:         str,
    doctor_id:        str,
    doctor_name:      str,
    patient_name:     str,
    treatment_key:    str,
    treatment_display: str,
    appointment_date: str,
) -> FollowUpState:
    state = FollowUpState(
        call_sid=call_sid,
        doctor_id=doctor_id,
        doctor_name=doctor_name,
        patient_name=patient_name,
        treatment_key=treatment_key,
        treatment_display=treatment_display,
        appointment_date=appointment_date,
    )
    followup_sessions[call_sid] = state
    logger.info(
        f"[FOLLOWUP] Session created | sid={call_sid} | "
        f"patient={patient_name} | treatment={treatment_key}"
    )
    return state


def get_followup_session(call_sid: str) -> Optional[FollowUpState]:
    return followup_sessions.get(call_sid)


def cleanup_followup_session(call_sid: str):
    if call_sid in followup_sessions:
        state = followup_sessions.pop(call_sid)
        _log_followup_summary(state)
        logger.info(f"[FOLLOWUP] Session cleaned up | sid={call_sid}")


# ─────────────────────────────────────────────────────────────────
# Treatment-specific follow-up knowledge
# Maps treatment_key → specific concerns the agent should probe
# ─────────────────────────────────────────────────────────────────

TREATMENT_CONTEXT: dict[str, dict] = {
    "root_canal": {
        "recovery_days": 3,
        "expected_symptoms": "some soreness and mild sensitivity around the treated tooth",
        "red_flags": "severe throbbing pain, significant swelling, fever, or pain that is getting worse after day 2",
        "medications": "antibiotics if prescribed, and pain relievers like ibuprofen or paracetamol",
        "diet_advice": "avoid chewing on the treated side, stick to soft foods",
        "urgent_if": "severe pain, swelling spreading to face or neck, fever above 38 degrees",
    },
    "tooth_extraction": {
        "recovery_days": 3,
        "expected_symptoms": "bleeding for the first few hours, swelling and soreness for 2 to 3 days",
        "red_flags": "heavy bleeding that won't stop, dry socket pain starting day 3 or 4, fever",
        "medications": "prescribed painkillers, antibiotics if given",
        "diet_advice": "liquid and soft diet, avoid straws, smoking, and spitting for 24 hours",
        "urgent_if": "non-stop bleeding, severe pain starting day 3, foul smell or taste",
    },
    "cavity_filling": {
        "recovery_days": 1,
        "expected_symptoms": "mild sensitivity to hot and cold for a day or two",
        "red_flags": "sensitivity lasting more than a week, sharp pain when biting, filling feels high",
        "medications": "usually none required",
        "diet_advice": "avoid very hot, cold, or hard foods for 24 hours",
        "urgent_if": "filling fell out, sharp pain when biting, sensitivity lasting more than a week",
    },
    "gum_treatment": {
        "recovery_days": 5,
        "expected_symptoms": "tender and swollen gums, some bleeding when brushing",
        "red_flags": "increasing pain after day 3, heavy bleeding, loose teeth",
        "medications": "antibiotics and antiseptic mouthwash if prescribed",
        "diet_advice": "soft foods, avoid spicy or acidic foods",
        "urgent_if": "severe pain, heavy bleeding, teeth becoming loose",
    },
    "tooth_pain": {
        "recovery_days": 1,
        "expected_symptoms": "reduced pain after examination or treatment",
        "red_flags": "pain is the same or worse, spreading to jaw or ear",
        "medications": "pain relief as recommended by doctor",
        "diet_advice": "avoid triggers identified during consultation",
        "urgent_if": "pain spreading to jaw, face, or neck, or fever",
    },
    "missing_tooth": {
        "recovery_days": 7,
        "expected_symptoms": "soreness and swelling at implant or bridge site",
        "red_flags": "implant mobility, severe pain, infection signs",
        "medications": "antibiotics and anti-inflammatories as prescribed",
        "diet_advice": "soft foods only, avoid chewing on implant side",
        "urgent_if": "implant feels loose, severe pain, swelling not reducing after day 3",
    },
    "dental_checkup": {
        "recovery_days": 0,
        "expected_symptoms": "no significant symptoms expected",
        "red_flags": "any pain or sensitivity noted during checkup worsening",
        "medications": "none unless prescribed",
        "diet_advice": "normal diet unless advised otherwise",
        "urgent_if": "any new pain, sensitivity, or swelling",
    },
    "cosmetic_dental": {
        "recovery_days": 2,
        "expected_symptoms": "mild sensitivity for a day or two after whitening or veneers",
        "red_flags": "severe sensitivity, veneer or crown feeling loose",
        "medications": "sensitivity toothpaste if recommended",
        "diet_advice": "avoid staining foods and drinks for 48 hours after whitening",
        "urgent_if": "veneer or crown fell off, severe pain",
    },
    "braces_alignment": {
        "recovery_days": 3,
        "expected_symptoms": "soreness and pressure on teeth for 3 to 5 days after adjustment",
        "red_flags": "wire poking into cheek or gum, bracket fell off",
        "medications": "over the counter pain relief as needed",
        "diet_advice": "soft foods for the first few days after adjustment",
        "urgent_if": "wire causing injury to mouth, severe pain",
    },
}

_DEFAULT_CONTEXT = {
    "recovery_days": 2,
    "expected_symptoms": "some mild discomfort",
    "red_flags": "severe pain, swelling, or fever",
    "medications": "as prescribed by the doctor",
    "diet_advice": "follow the doctor's instructions",
    "urgent_if": "severe pain, swelling, or fever",
}


def _get_treatment_context(treatment_key: str) -> dict:
    return TREATMENT_CONTEXT.get(treatment_key, _DEFAULT_CONTEXT)


# ─────────────────────────────────────────────────────────────────
# System prompt builder
# ─────────────────────────────────────────────────────────────────

def _build_system_prompt(state: FollowUpState) -> str:
    ctx = _get_treatment_context(state.treatment_key)

    return f"""You are a warm, professional dental clinic AI assistant calling on behalf of Dr. {state.doctor_name}'s clinic.

You are conducting a post-treatment follow-up call with {state.patient_name}, who had a {state.treatment_display} on {state.appointment_date}.

YOUR PERSONALITY:
- Warm, caring, and conversational — like a concerned clinic nurse
- Patient and understanding — never rushed
- Speak in clear, simple language a patient can understand over the phone
- Keep each response SHORT — 1 to 3 sentences maximum (this is a phone call)
- Ask ONE question at a time
- Never use medical jargon without explaining it

YOUR GOALS (in order):
1. Confirm you are speaking with {state.patient_name}
2. Check if they are experiencing any pain or discomfort
3. Understand the nature of any pain (location, severity 1-10, type)
4. Confirm they are taking their prescribed medication
5. Check for swelling or bleeding
6. Check if they can eat and drink normally
7. Ask if they have any other concerns
8. Give appropriate advice and close the call warmly

TREATMENT-SPECIFIC KNOWLEDGE for {state.treatment_display}:
- Expected recovery time: {ctx['recovery_days']} days
- Normal symptoms: {ctx['expected_symptoms']}
- Warning signs to listen for: {ctx['red_flags']}
- Medications patient should be taking: {ctx['medications']}
- Diet advice: {ctx['diet_advice']}
- Needs URGENT clinic attention if patient reports: {ctx['urgent_if']}

IMPORTANT RULES:
- If the patient reports ANY of the urgent symptoms, immediately say:
  "I am going to flag this for Dr. {state.doctor_name} right away. Please also call the clinic directly at your earliest convenience."
  Then end the call gracefully.
- If they say they are NOT taking their medication, understand why and gently encourage them
- If they sound distressed or in serious pain, prioritize getting them urgent care
- Do NOT offer diagnoses — you can acknowledge symptoms and advise them to call the clinic
- Never ask multiple questions in one turn
- This is a voice call — no bullet points, no markdown, no asterisks, no emojis
- Natural spoken sentences only

CURRENT CONVERSATION STAGE: {state.stage.name}

You have gathered so far:
- Pain reported: {state.pain_reported}
- Pain severity: {state.pain_severity}
- Taking medication: {state.taking_medication}
- Swelling reported: {state.swelling_reported}
- Eating normally: {state.eating_normally}
"""


# ─────────────────────────────────────────────────────────────────
# Core conversation engine
# ─────────────────────────────────────────────────────────────────

def _call_groq(system_prompt: str, history: list[dict]) -> str:
    """Call Groq with full conversation history. Returns agent reply text."""
    try:
        response = httpx.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL_NAME,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    *history,
                ],
                "max_tokens": 150,   # short responses for voice
                "temperature": 0.4,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()

    except Exception as e:
        logger.error(f"[FOLLOWUP] Groq error: {e}")
        return "I'm sorry, I'm having a little trouble. Could you repeat that please?"


def _extract_structured_data(state: FollowUpState, patient_message: str):
    """
    After each patient turn, extract structured data from what they said.
    Updates state fields directly. Uses a lightweight Groq call.
    """
    extract_prompt = f"""Extract structured data from this patient statement during a post-dental follow-up call.

Patient said: "{patient_message}"
Current stage: {state.stage.name}
Treatment: {state.treatment_display}

Reply with ONLY a JSON object with these keys (use null if not mentioned):
{{
  "pain_reported": true/false/null,
  "pain_severity": "mild"/"moderate"/"severe"/null,
  "pain_location": "string or null",
  "pain_type": "throbbing/sharp/dull/burning/string or null",
  "taking_medication": true/false/null,
  "medication_issue": "string or null",
  "swelling_reported": true/false/null,
  "eating_normally": true/false/null,
  "urgent_flag": true/false,
  "open_concerns": "string or null"
}}

urgent_flag should be true if the patient mentions: severe pain, fever, heavy bleeding, spreading swelling, pus, or inability to swallow/breathe."""

    try:
        response = httpx.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL_NAME,
                "messages": [
                    {"role": "user", "content": extract_prompt}
                ],
                "max_tokens": 200,
                "temperature": 0.0,
            },
            timeout=8.0,
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"].strip()

        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        data = json.loads(text)

        # Update state only if value is not None
        if data.get("pain_reported")     is not None: state.pain_reported     = data["pain_reported"]
        if data.get("pain_severity")     is not None: state.pain_severity     = data["pain_severity"]
        if data.get("pain_location")     is not None: state.pain_location     = data["pain_location"]
        if data.get("pain_type")         is not None: state.pain_type         = data["pain_type"]
        if data.get("taking_medication") is not None: state.taking_medication = data["taking_medication"]
        if data.get("medication_issue")  is not None: state.medication_issue  = data["medication_issue"]
        if data.get("swelling_reported") is not None: state.swelling_reported = data["swelling_reported"]
        if data.get("eating_normally")   is not None: state.eating_normally   = data["eating_normally"]
        if data.get("open_concerns")     is not None: state.open_concerns     = data["open_concerns"]
        if data.get("urgent_flag"):
            state.needs_urgent_attention = True

    except Exception as e:
        logger.warning(f"[FOLLOWUP] Extraction failed (non-critical): {e}")


def _advance_stage(state: FollowUpState):
    """
    Move to the next stage based on what data has been collected.
    Skips stages that are no longer needed.
    """
    current = state.stage

    if current == FollowUpStage.GREETING:
        state.stage = FollowUpStage.PAIN_CHECK

    elif current == FollowUpStage.PAIN_CHECK:
        if state.pain_reported:
            state.stage = FollowUpStage.PAIN_DETAILS
        else:
            state.stage = FollowUpStage.MEDICATION

    elif current == FollowUpStage.PAIN_DETAILS:
        state.stage = FollowUpStage.MEDICATION

    elif current == FollowUpStage.MEDICATION:
        if state.taking_medication is False:
            state.stage = FollowUpStage.MEDICATION_ISSUE
        else:
            state.stage = FollowUpStage.SWELLING

    elif current == FollowUpStage.MEDICATION_ISSUE:
        state.stage = FollowUpStage.SWELLING

    elif current == FollowUpStage.SWELLING:
        state.stage = FollowUpStage.EATING

    elif current == FollowUpStage.EATING:
        state.stage = FollowUpStage.OPEN_CONCERNS

    elif current == FollowUpStage.OPEN_CONCERNS:
        state.stage = FollowUpStage.CLOSE

    elif current == FollowUpStage.CLOSE:
        state.stage = FollowUpStage.DONE


# ─────────────────────────────────────────────────────────────────
# Public API — called from voice_routes.py
# ─────────────────────────────────────────────────────────────────

def process_followup_input(call_sid: str, speech_text: str) -> str:
    """
    Main entry point. Call this from the outbound gather webhook.

    Returns:
      - The agent's next spoken reply (clean text, no markdown)
      - Empty string if the call should end (stage == DONE)
    """
    state = get_followup_session(call_sid)
    if not state:
        logger.error(f"[FOLLOWUP] No session for sid={call_sid}")
        return "I'm sorry, there was an error with this call. Goodbye."

    state.turn_count += 1

    # Safety: end call if too many turns
    if state.turn_count > state.MAX_TURNS:
        state.stage = FollowUpStage.DONE
        return (
            f"Thank you so much for your time, {state.patient_name}. "
            "We will pass your feedback on to the doctor. Take care and feel better soon. Goodbye."
        )

    # Add patient message to history
    if speech_text and speech_text.strip():
        state.history.append({"role": "user", "content": speech_text.strip()})

        # Extract structured data from what patient said
        _extract_structured_data(state, speech_text.strip())

        # If urgent flag was raised, escalate immediately
        if state.needs_urgent_attention:
            ctx = _get_treatment_context(state.treatment_key)
            urgent_reply = (
                f"I'm concerned about what you've described. "
                f"I'm flagging this for Dr. {state.doctor_name} right away. "
                f"Please also call the clinic directly as soon as possible. "
                f"You should go to the clinic or an emergency dentist if {ctx['urgent_if']}. "
                f"Thank you for letting us know. Please take care of yourself. Goodbye."
            )
            state.stage = FollowUpStage.DONE
            state.history.append({"role": "assistant", "content": urgent_reply})
            _log_followup_summary(state)
            return urgent_reply

        # Advance stage after processing patient input
        _advance_stage(state)

    # If call is done
    if state.stage == FollowUpStage.DONE:
        return ""

    # Build system prompt with current context and get Groq response
    system_prompt = _build_system_prompt(state)
    reply = _call_groq(system_prompt, state.history)

    # Clean reply for TTS (no markdown, no emojis)
    reply = _clean_for_tts(reply)

    # Add agent reply to history
    state.history.append({"role": "assistant", "content": reply})

    logger.info(
        f"[FOLLOWUP] Turn {state.turn_count} | sid={call_sid} | "
        f"stage={state.stage.name} | reply='{reply[:80]}'"
    )

    return reply


def get_opening_message(state: FollowUpState) -> str:
    """
    Generate the very first thing the agent says when the patient picks up.
    This is spoken before any patient input.
    """
    opening = (
        f"Hello, may I speak with {state.patient_name} please? "
        f"This is an automated follow-up call from Dr. {state.doctor_name}'s dental clinic, "
        f"checking in after your recent {state.treatment_display}."
    )
    state.history.append({"role": "assistant", "content": opening})
    return opening


def is_followup_done(call_sid: str) -> bool:
    state = get_followup_session(call_sid)
    if not state:
        return True
    return state.stage == FollowUpStage.DONE


# ─────────────────────────────────────────────────────────────────
# Summary logger — writes structured summary when call ends
# ─────────────────────────────────────────────────────────────────

def _log_followup_summary(state: FollowUpState):
    """
    Log a structured follow-up summary.
    In production: save this to a DB table (follow_up_reports).
    Currently logs to the application logger and can be extended.
    """
    summary = {
        "call_sid":               state.call_sid,
        "doctor_id":              state.doctor_id,
        "patient_name":           state.patient_name,
        "treatment":              state.treatment_display,
        "appointment_date":       state.appointment_date,
        "follow_up_timestamp":    datetime.utcnow().isoformat(),
        "pain_reported":          state.pain_reported,
        "pain_severity":          state.pain_severity,
        "pain_location":          state.pain_location,
        "pain_type":              state.pain_type,
        "taking_medication":      state.taking_medication,
        "medication_issue":       state.medication_issue,
        "swelling_reported":      state.swelling_reported,
        "eating_normally":        state.eating_normally,
        "open_concerns":          state.open_concerns,
        "needs_urgent_attention": state.needs_urgent_attention,
        "total_turns":            state.turn_count,
    }

    logger.info(f"[FOLLOWUP] SUMMARY | {json.dumps(summary, ensure_ascii=False)}")

    # ── TODO: persist to DB ───────────────────────────────────────
    # When you add the follow_up_reports table, replace the logger
    # call above with something like:
    #
    #   from db.repository import save_followup_report
    #   save_followup_report(**summary)
    #
    # The summary dict maps 1:1 to the columns you'd want.
    # ─────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────
# TTS cleaner (mirrors voice_agent.py)
# ─────────────────────────────────────────────────────────────────

def _clean_for_tts(text: str) -> str:
    text = re.sub(r"[^\x00-\x7F]+", "", text)
    text = re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", text)
    text = re.sub(r"#{1,3}\s?", "", text)
    text = re.sub(r"\n{2,}", " ", text).strip()
    return text