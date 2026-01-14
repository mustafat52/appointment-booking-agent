import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse

from schema import ChatRequest, ChatResponse
from agent import run_agent
from state import BookingState
from typing import Dict

from calendar_oauth import get_oauth_flow
from auth_store import oauth_store

# Phase 3 – Step 3.2
from doctor_config import DOCTORS, DEFAULT_DOCTOR_ID

app = FastAPI()

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def serve_ui():
    return FileResponse("static/index.html")


# session_id -> BookingState
state_store: Dict[str, BookingState] = {}


# -------------------------------
# Doctor resolution helper
# -------------------------------
def get_doctor_or_404(doctor_slug: str):
    doctor = DOCTORS.get(doctor_slug)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return doctor


# -------------------------------
# Doctor-specific booking URL
# -------------------------------
@app.get("/book/{doctor_slug}")
def serve_doctor_ui(doctor_slug: str):
    # Validate doctor exists
    get_doctor_or_404(doctor_slug)

    # Serve SAME UI (doctor context wired in Step 3.3)
    return FileResponse("static/index.html")


# -------------------------------
# Chat endpoint (unchanged)
# -------------------------------
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    session_id = req.session_id

    if session_id not in state_store:
        state_store[session_id] = BookingState()

    state = state_store[session_id]

    reply = run_agent(req.message, state)

    if state.confirmed:
        state.reset()

    return ChatResponse(reply=reply)


# -------------------------------
# OAuth – connect calendar
# -------------------------------
@app.get("/connect-calendar")
def connect_calendar():
    flow = get_oauth_flow()

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    oauth_store["flow"] = flow
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

    oauth_store["credentials"] = flow.credentials

    return {"status": "Calendar connected successfully 🎉"}
