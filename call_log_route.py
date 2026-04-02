# ═══════════════════════════════════════════════════════════════
# call_log_route.py
# ─────────────────────────────────────────────────────────────────
# Optional: adds /voice/calls/log  →  pulls recent calls from Twilio
# Add to main.py (or voice_routes.py) as needed.
#
#   from call_log_route import call_log_router
#   app.include_router(call_log_router)
#
# ═══════════════════════════════════════════════════════════════

import os
from fastapi import APIRouter, Request, HTTPException
from twilio.rest import Client as TwilioClient

call_log_router = APIRouter(tags=["voice"])


@call_log_router.get("/voice/calls/log")
async def get_call_log(request: Request, limit: int = 25):
    """
    Returns recent calls from Twilio account.
    Requires doctor session.
    """
    from main import require_doctor
    try:
        require_doctor(request)
    except HTTPException:
        raise HTTPException(status_code=401, detail="Not authenticated")

    sid   = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")

    if not sid or not token:
        raise HTTPException(status_code=500, detail="Twilio credentials not configured")

    client = TwilioClient(sid, token)

    calls = client.calls.list(limit=limit)

    return [
        {
            "call_sid":    c.sid,
            "from_number": c.from_formatted,
            "to_number":   c.to_formatted,
            "direction":   c.direction,
            "status":      c.status,
            "duration":    c.duration,
            "started_at":  str(c.start_time) if c.start_time else None,
        }
        for c in calls
    ]
