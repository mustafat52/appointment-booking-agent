from config import MODEL_NAME
from state import BookingState
from tools import check_availability, book_appointment
import google.generativeai as genai
import json
from datetime import date

# Initialize Gemini model
model = genai.GenerativeModel(MODEL_NAME)


def extract_with_gemini(user_message: str):
    """
    Extract intent, date, and time from user message using Gemini.
    """

    # ✅ IMPORTANT: compute TODAY dynamically (NOT at import time)
    today = date.today().isoformat()

    prompt = f"""
You are an information extraction system.

TODAY'S DATE IS: {today}

Your job is to detect appointment booking intent.

If the user wants to:
- book
- schedule
- make an appointment
- reserve a slot

Then intent MUST be "BOOK".

Return ONLY valid JSON.

Schema:
{{"intent": "BOOK or UNKNOWN",
  "date": "YYYY-MM-DD or null",
  "time": "HH:MM or null"
}}

Rules:
- "tomorrow", "next Friday", etc. must be converted relative to TODAY'S DATE
- "evening" means time is null
- If booking intent is clear, DO NOT return UNKNOWN

Message:
{user_message}
"""

    response = model.generate_content(prompt)

    try:
        text = response.text.strip()

        # ✅ Remove markdown fences if Gemini adds them
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()

        return json.loads(text)

    except Exception as e:
        print("❌ GEMINI PARSE ERROR:", e)
        print("❌ RAW GEMINI OUTPUT:", response.text)

        return {
            "intent": "UNKNOWN",
            "date": None,
            "time": None
        }


def run_agent(user_message: str, state: BookingState) -> str:
    """
    Core agent logic.
    """

    # 1️⃣ Extract intent/date/time using Gemini
    extracted = extract_with_gemini(user_message)

    print("🧠 EXTRACTED:", extracted)

    # 2️⃣ Fallback intent detection (ONLY if Gemini failed)
    if extracted["intent"] == "UNKNOWN":
        booking_keywords = [
            "book", "appointment", "schedule", "reserve",
            "tomorrow", "today", "next"
        ]
        for word in booking_keywords:
            if word in user_message.lower():
                extracted["intent"] = "BOOK"
                break

    # 3️⃣ Update booking state
    if extracted["intent"] == "BOOK":
        state.intent = "BOOK"

    if extracted.get("date"):
        state.date = extracted["date"]

    if extracted.get("time"):
        state.time = extracted["time"]

    print("📦 STATE:", state.__dict__)

    # 4️⃣ Ask for missing info
    if state.intent == "BOOK" and not state.date:
        return "Sure 🙂 What date would you like to book?"

    if state.intent == "BOOK" and not state.time:
        return "Got it. What time should I book?"

    # 5️⃣ Final availability check + booking
    if state.is_complete():
        print("🔍 FINAL CHECK:", state.date, state.time)

        if not check_availability(state.date, state.time):
            return "❌ That slot is not available. Please choose another time."

        booking = book_appointment(state.date, state.time)
        state.confirmed = True

        return (
            f"✅ Your appointment is confirmed!\n"
            f"📅 Date: {booking['date']}\n"
            f"⏰ Time: {booking['time']}"
        )

    # 6️⃣ Fallback
    return "How can I help you today?"
