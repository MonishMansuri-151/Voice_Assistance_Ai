
import os
import io
import base64
import time
from google.genai import errors
from google import genai
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from elevenlabs.client import ElevenLabs


# =========================================================
# ENVIRONMENT
# =========================================================

load_dotenv(override=True)

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
VOICE_ID = os.getenv(
    "ELEVENLABS_VOICE_ID",
    "JBFqnCBsd6RMkjVDRZzb"
).strip()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
# GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.6-flash"
).strip()


# =========================================================
# STARTUP DIAGNOSTICS
# Never print API keys
# =========================================================

print("========================================")
print("Voice Assistant Configuration")
print("========================================")
print("ElevenLabs key loaded:", bool(ELEVENLABS_API_KEY))
print("Gemini key loaded:", bool(GEMINI_API_KEY))
print("Gemini model:", GEMINI_MODEL)
print("========================================")


# =========================================================
# APP
# =========================================================

app = FastAPI(title="Voice Assistant AI")

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

templates = Jinja2Templates(directory="templates")


# =========================================================
# API CLIENTS
# =========================================================

eleven = (
    ElevenLabs(api_key=ELEVENLABS_API_KEY)
    if ELEVENLABS_API_KEY else None
)

gemini_client = (
    genai.Client(api_key=GEMINI_API_KEY)
    if GEMINI_API_KEY else None
)


# =========================================================
# HOME
# =========================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )


# =========================================================
# VOICE ASSISTANT
# =========================================================

@app.post("/api/voice")
async def voice_assistant(audio: UploadFile = File(...)):

    if not eleven:
        raise HTTPException(
            status_code=500,
            detail="ELEVENLABS_API_KEY .env mein set nahi hai."
        )

    if not gemini_client:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY .env mein set nahi hai."
        )

    raw_audio = await audio.read()

    if not raw_audio:
        raise HTTPException(
            status_code=400,
            detail="Audio record nahi hui. Dobara try karein."
        )

    if len(raw_audio) > 15 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="Audio file bahut badi hai. Chhoti recording karein."
        )

    try:
        # 1. SPEECH TO TEXT: ELEVENLABS

        print("Sending audio to ElevenLabs...")

        transcription = eleven.speech_to_text.convert(
            file=io.BytesIO(raw_audio),
            model_id="scribe_v1"
        )

        user_text = (
            getattr(transcription, "text", "") or ""
        ).strip()

        print("Transcript:", user_text)

        if not user_text:
            raise HTTPException(
                status_code=400,
                detail="Aapki awaaz samajh nahi aayi."
            )

        # 2. AI RESPONSE: GEMINI

        # print("Sending text to Gemini...")

        # result = gemini_client.models.generate_content(
        #     model=GEMINI_MODEL,
        #     contents=(
        #         "You are a friendly voice assistant. "
        #         "Reply clearly and naturally. "
        #         "Match the user's language. "
        #         "Use Hindi or Hinglish when appropriate. "
        #         "Keep spoken replies concise and natural.\n\n"
        #         f"User: {user_text}"
        #     )
        # )

        # reply = (result.text or "").strip()

        # if not reply:
        #     raise HTTPException(
        #         status_code=502,
        #         detail="Gemini ne empty response diya."
        #     )

        # print("Assistant:", reply)
                # 2. TEXT → AI RESPONSE: GEMINI

        import time
        from google.genai import errors

        print("Sending text to Gemini...")

        prompt = (
            "You are a friendly voice assistant. "
            "Reply clearly and naturally. "
            "Match the user's language. "
            "Use Hindi or Hinglish when appropriate. "
            "Keep spoken replies concise and natural.\n\n"
            f"User: {user_text}"
        )

        reply = ""

        for attempt in range(3):
            try:
                result = gemini_client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt
                )

                reply = (result.text or "").strip()

                if reply:
                    break

                raise HTTPException(
                    status_code=502,
                    detail="Gemini ne empty response diya."
                )

            except errors.APIError as exc:
                if getattr(exc, "code", None) != 503:
                    raise

                if attempt == 2:
                    raise

                wait_seconds = 2 ** (attempt + 1)

                print(
                    f"Gemini busy. {wait_seconds} seconds baad retry..."
                )

                time.sleep(wait_seconds)

        if not reply:
            raise HTTPException(
                status_code=502,
                detail="Gemini se jawab nahi mila."
            )

        print("Assistant:", reply)

        # 3. TEXT TO SPEECH: ELEVENLABS

        print("Generating ElevenLabs voice...")

        audio_chunks = eleven.text_to_speech.convert(
            text=reply,
            voice_id=VOICE_ID,
            model_id="eleven_flash_v2_5",
            output_format="mp3_44100_128"
        )

        audio_bytes = b"".join(audio_chunks)

        if not audio_bytes:
            raise HTTPException(
                status_code=502,
                detail="ElevenLabs ne audio response nahi diya."
            )

        print("Voice response generated successfully.")

        # 4. RESPONSE

        return {
            "transcript": user_text,
            "reply": reply,
            "audio_base64": base64.b64encode(
                audio_bytes
            ).decode("utf-8"),
            "audio_mime_type": "audio/mpeg"
        }

    except HTTPException:
        raise

    except Exception as exc:
        # Error terminal mein dikhega, API key nahi
        print("Voice assistant error:", repr(exc))

        raise HTTPException(
            status_code=502,
            detail=(
                "Voice request fail hui. "
                "Terminal mein error check karein."
            )
        )
