import os
import base64
import logging
import httpx

logger = logging.getLogger("medschedule")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Gemini free-tier models
# - gemini-1.5-flash  → supports text + vision, very fast, generous free quota
GEMINI_MODEL   = "gemini-1.5-flash"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1/models/{GEMINI_MODEL}:generateContent"

DENTAL_SYSTEM_PROMPT = """You are DentalAssist AI, a friendly and knowledgeable dental health assistant 
for a smart dental management system. Your role is to help patients understand their dental symptoms 
BEFORE they see a dentist.

Your responsibilities:
1. Listen carefully to the patient's dental complaint in plain language OR analyse the dental image they share
2. Identify the likely dental issue (e.g., cavity, gum disease, abscess, sensitivity, wisdom tooth, etc.)
3. Assess the SERIOUSNESS: Low / Moderate / High / Emergency
4. Provide simple PRECAUTIONS they can take at home right now
5. Tell them WHAT TYPE of dental appointment to book (routine checkup, urgent, emergency)
6. Always recommend booking an appointment with a dentist — never replace professional advice

If the user shares an IMAGE:
- Describe what you can visually observe in simple terms (discoloration, swelling, gum recession, etc.)
- Give your best assessment based on visual evidence
- Be extra clear that visual AI analysis is not a substitute for an in-person exam

Response format (always structured like this):
🦷 **Possible Issue:** [what it might be, in simple terms]
⚠️ **Seriousness:** [Low / Moderate / High / Emergency] — [1 sentence why]
💊 **What you can do now:** [2-3 practical home precautions]
📅 **Next step:** [type of appointment to book + urgency]
💬 **Note:** [1 reassuring line reminding them this is AI guidance, not a diagnosis]

Rules:
- Always respond in a warm, calm, non-alarming tone
- Use simple everyday language — no medical jargon
- If symptoms suggest a dental emergency (severe pain, swelling, fever, trauma), say so clearly
- Keep responses concise — under 220 words
- Never diagnose definitively; always say "this could be" or "it looks like"
- If the question/image is not dental-related, gently redirect: "I'm only able to help with dental concerns!"
"""


def _build_parts(user_message: str, image_bytes: bytes | None, image_content_type: str) -> list:
    """
    Build the Gemini API 'parts' list.
    Gemini accepts inline image data directly — no base64 data URL needed,
    just raw base64 + mimeType in an inlineData block.
    """
    parts = []

    if image_bytes:
        parts.append({
            "inlineData": {
                "mimeType": image_content_type,
                "data": base64.b64encode(image_bytes).decode("utf-8"),
            }
        })

    text = user_message.strip() or (
        "Please analyse this dental image and tell me what you see." if image_bytes else ""
    )
    if text:
        parts.append({"text": text})

    return parts


async def get_dental_ai_response(
    user_message: str,
    image_bytes: bytes | None = None,
    image_content_type: str = "image/jpeg",
) -> str:
    """
    Sends user message (and optionally an image) to Gemini API.

    - image_bytes provided  → multimodal (image + text)
    - text only             → text-only request

    Both use the same gemini-1.5-flash model (free tier).
    Returns the AI response string.
    """
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not set in environment")
        return "⚠️ AI assistant is currently unavailable. Please call us or book an appointment directly."

    parts = _build_parts(user_message, image_bytes, image_content_type)

    if not parts:
        return "⚠️ Please send a message or an image so I can help you!"

    # v1 API does not support system_instruction.
    # We inject the system prompt as the first user/model exchange instead.
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": DENTAL_SYSTEM_PROMPT}],
            },
            {
                "role": "model",
                "parts": [{"text": "Understood! I am DentalAssist AI. I am ready to help patients with their dental concerns. Please share your symptoms or a dental image."}],
            },
            {
                "role": "user",
                "parts": parts,
            },
        ],
        "generationConfig": {
            "maxOutputTokens": 450,
            "temperature": 0.5,
        },
    }

    url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data  = response.json()
            reply = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            logger.info(
                f"Dental AI response generated | model={GEMINI_MODEL} | vision={'yes' if image_bytes else 'no'}"
            )
            return reply

    except httpx.TimeoutException:
        logger.warning("Gemini API timed out")
        return "⏱️ The AI is taking a bit longer than usual. Please try again in a moment."

    except httpx.HTTPStatusError as e:
        logger.error(f"Gemini API HTTP error: {e.response.status_code} — {e.response.text}")
        return "⚠️ AI assistant is temporarily unavailable. Please try again shortly."

    except (KeyError, IndexError) as e:
        logger.error(f"Unexpected Gemini response structure: {e}")
        return "⚠️ Received an unexpected response from AI. Please try again."

    except Exception as e:
        logger.exception(f"Unexpected error in dental AI service: {str(e)}")
        return "⚠️ Something went wrong. Please try again or contact us directly."