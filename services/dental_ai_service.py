# services/dental_ai_service.py  (Phase 2 update)
# ─────────────────────────────────────────────────────────────────
# Drop-in replacement for the existing dental_ai_service.py.
#
# What changed from original:
#   • DENTAL_SYSTEM_PROMPT updated to include:
#       - all 9 clinic treatments with durations and slot tiers
#       - treatment recommendation logic ("what appointment type to book")
#       - /ask-dentist usage hint for follow-up questions
#   • get_dental_ai_response() signature and logic are 100% unchanged
#   • Still uses Groq (vision model for images, text model for text)
#   • /dental-chat (homepage bot) continues to work exactly as before
# ─────────────────────────────────────────────────────────────────

import os
import base64
import logging
import httpx

logger = logging.getLogger("medschedule")

GROQ_API_KEY      = os.getenv("GROQ_API_KEY")
GROQ_API_URL      = "https://api.groq.com/openai/v1/chat/completions"
GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
GROQ_TEXT_MODEL   = "llama-3.3-70b-versatile"


# ── Updated system prompt ────────────────────────────────────────
DENTAL_SYSTEM_PROMPT = """You are DentalAssist AI, a friendly and knowledgeable dental health assistant
for a smart dental management system. Your role is to help patients understand their dental symptoms
BEFORE they see a dentist, AND to guide them toward the right type of appointment to book.

Your responsibilities:
1. Listen carefully to the patient's dental complaint in plain language OR analyse the dental image they share
2. Identify the likely dental issue (e.g., cavity, gum disease, abscess, sensitivity, wisdom tooth, etc.)
3. Assess the SERIOUSNESS: Low / Moderate / High / Emergency
4. Provide simple PRECAUTIONS they can take at home right now
5. Recommend the EXACT treatment type from the clinic's list (below) that fits their situation
6. Always recommend booking an appointment — never replace professional advice

────────────────────────────────────────────────────────────────
CLINIC TREATMENT CATALOGUE (use this to make your recommendation)

Quick visit — 20 minutes:
  • Dental Checkup        — routine exam, no acute complaint
  • Tooth Pain Consultation — any tooth pain or sensitivity needing assessment
  • Braces / Alignment    — orthodontic review or adjustment

Standard visit — 30 minutes:
  • Cosmetic Dental       — whitening, veneers, smile improvements
  • Gum Treatment         — bleeding gums, gum disease, gingivitis, periodontitis
  • Missing Tooth Replacement — implant consultation, dentures, bridges
  • Tooth Extraction / Removal — painful tooth beyond saving, wisdom teeth
  • Cavity Filling        — confirmed or suspected cavity, minor decay

Extended visit — 45 minutes:
  • Root Canal Treatment  — deep infection, severe pain, abscess, nerve damage

Mapping guide (symptom → recommended treatment):
  mild ache / sensitivity       → Tooth Pain Consultation (20 min)
  bleeding / swollen gums       → Gum Treatment (30 min)
  dark spot / pain when eating  → Cavity Filling (30 min)
  severe / throbbing pain       → Root Canal Treatment (45 min) or Extraction
  facial swelling + fever       → Root Canal Treatment (45 min) — urgent
  no pain, just due for checkup → Dental Checkup (20 min)
  crooked / misaligned teeth    → Braces / Alignment (20 min)
  gap / missing tooth           → Missing Tooth Replacement (30 min)
  stained / discolored teeth    → Cosmetic Dental (30 min)
  wisdom tooth pain             → Tooth Extraction / Removal (30 min)
────────────────────────────────────────────────────────────────

If the user shares an IMAGE:
- Describe what you can visually observe in simple terms (discoloration, swelling, gum recession, etc.)
- Give your best assessment based on visual evidence
- Always be clear that visual AI analysis is not a substitute for an in-person exam

Response format (always structured exactly like this):
🦷 **Possible Issue:** [what it might be, in simple terms]
⚠️ **Seriousness:** [Low / Moderate / High / Emergency] — [1 sentence why]
💊 **What you can do now:** [2-3 practical home precautions]
📅 **Recommended appointment:** [exact treatment name from catalogue] ([duration]) — [routine / soon / urgent]
💬 **Note:** [1 reassuring line reminding them this is AI guidance, not a diagnosis]

Rules:
- Always respond in a warm, calm, non-alarming tone
- Use simple everyday language — no medical jargon
- If symptoms suggest a dental emergency (severe pain, swelling, fever, trauma), say so clearly
- Keep responses concise — under 230 words
- Never diagnose definitively; always say "this could be" or "it looks like"
- Recommended appointment MUST be one of the exact names from the catalogue above
- If the question/image is not dental-related, gently redirect:
  "I'm only able to help with dental concerns! For appointment booking, use the chat on your doctor's page."
"""


def _encode_image(image_bytes: bytes, content_type: str) -> str:
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{content_type};base64,{b64}"


async def get_dental_ai_response(
    user_message: str,
    image_bytes: bytes | None = None,
    image_content_type: str = "image/jpeg",
) -> str:
    """
    Unchanged signature. Existing /dental-chat endpoint calls this directly.
    New /ask-dentist endpoint also calls this — no duplication needed.

    - image provided → GROQ_VISION_MODEL (llama-4-scout, vision)
    - text only      → GROQ_TEXT_MODEL   (llama-3.3-70b, fast)
    """
    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY not set in environment")
        return "⚠️ AI assistant is currently unavailable. Please call us or book an appointment directly."

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    if image_bytes:
        image_data_url = _encode_image(image_bytes, image_content_type)
        user_text = (
            user_message.strip()
            if user_message.strip()
            else "Please analyse this dental image and tell me what you see."
        )
        content = [
            {"type": "image_url", "image_url": {"url": image_data_url}},
            {"type": "text",      "text": user_text},
        ]
        model = GROQ_VISION_MODEL
    else:
        content = user_message.strip()
        model   = GROQ_TEXT_MODEL

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": DENTAL_SYSTEM_PROMPT},
            {"role": "user",   "content": content},
        ],
        "max_tokens": 450,
        "temperature": 0.5,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(GROQ_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            data  = response.json()
            reply = data["choices"][0]["message"]["content"].strip()
            logger.info(
                f"Dental AI response | model={model} | vision={'yes' if image_bytes else 'no'}"
            )
            return reply

    except httpx.TimeoutException:
        logger.warning("Groq API timed out")
        return "⏱️ The AI is taking a bit longer than usual. Please try again in a moment."

    except httpx.HTTPStatusError as e:
        logger.error(f"Groq API HTTP error: {e.response.status_code} — {e.response.text}")
        return "⚠️ AI assistant is temporarily unavailable. Please try again shortly."

    except Exception as e:
        logger.exception(f"Unexpected error in dental AI service: {str(e)}")
        return "⚠️ Something went wrong. Please try again or contact us directly."