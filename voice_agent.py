# voice_agent.py
# ─────────────────────────────────────────────────────────────────
# MedScheduler AI – Twilio Voice Calling Agent
# Handles inbound phone calls for booking & cancelling appointments.
# Reuses ALL existing agent logic — state, tools, extractor.
# NO existing files are modified.
# ─────────────────────────────────────────────────────────────────

import logging
import re
from state import BookingState
from agent import run_agent

logger = logging.getLogger("medschedule.voice")

# ──────────────────────────────────────────────
# In-memory call sessions  (call_sid → state)
# ──────────────────────────────────────────────
call_sessions: dict[str, BookingState] = {}


def get_or_create_call_state(call_sid: str, doctor_id: str, doctor_name: str) -> BookingState:
    """
    Return existing call session or create a fresh one.
    Doctor context is injected immediately so run_agent never sees a missing doctor.
    """
    if call_sid not in call_sessions:
        s = BookingState()
        s.doctor_id = doctor_id
        s.doctor_name = doctor_name
        call_sessions[call_sid] = s
        logger.info(f"[VOICE] New call session | sid={call_sid} | doctor={doctor_id}")
    return call_sessions[call_sid]


def cleanup_call_session(call_sid: str):
    """Remove session when call ends (Twilio status callback)."""
    if call_sid in call_sessions:
        del call_sessions[call_sid]
        logger.info(f"[VOICE] Session cleaned up | sid={call_sid}")


def process_voice_input(call_sid: str, speech_text: str, doctor_id: str, doctor_name: str) -> str:
    """
    Core voice turn processor.
    - Retrieves/creates call state
    - Runs through the SAME run_agent() used by web & WhatsApp channels
    - Returns plain-text reply (TwiML Say will read it aloud)
    """
    state = get_or_create_call_state(call_sid, doctor_id, doctor_name)

    if not speech_text or speech_text.strip() == "":
        return "I'm sorry, I didn't catch that. Could you please repeat?"

    # Strip emojis / markdown before speaking — phone callers hear TTS
    reply = run_agent(speech_text.strip(), state)
    reply = _clean_for_tts(reply)

    logger.info(
        f"[VOICE] Processed | sid={call_sid} | input='{speech_text[:60]}' | reply='{reply[:80]}'"
    )
    return reply


def _clean_for_tts(text: str) -> str:
    """
    Remove emoji, markdown bold/italic, bullet symbols so Twilio TTS
    reads natural speech instead of 'asterisk asterisk'.
    """
    # Remove emoji (basic unicode range)
    text = re.sub(r"[^\x00-\x7F]+", "", text)
    # Remove markdown bold/italic
    text = re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", text)
    # Replace bullet-style lines
    text = text.replace("1️⃣", "option 1,").replace("2️⃣", "option 2,").replace("3️⃣", "option 3,")
    # Collapse multiple blank lines
    text = re.sub(r"\n{2,}", "\n", text).strip()
    return text
