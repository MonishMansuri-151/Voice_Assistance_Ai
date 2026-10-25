
import os
from pathlib import Path
import io
import json
import base64
import time
from datetime import date

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from elevenlabs.client import ElevenLabs
from google import genai
from google.genai import errors

from database import get_connection

load_dotenv(override=True)

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
VOICE_ID = os.getenv(
    "ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb"
).strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL", "gemini-2.5-flash"
).strip()

app = FastAPI(title="Voice Assistant Hotel Booking")

# app.mount("/static", StaticFiles(directory="static"), name="static")
# templates = Jinja2Templates(directory="templates")
BASE_DIR = Path(__file__).resolve().parent

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static"
)

templates = Jinja2Templates(
    directory=str(BASE_DIR / "templates")
)

eleven = ElevenLabs(api_key=ELEVENLABS_API_KEY) if ELEVENLABS_API_KEY else None
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Temporary conversation state for development.
# Use Redis or a database for production and multiple workers.
sessions = {}


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )


def gemini_json(prompt):
    """Ask Gemini to extract booking information as JSON."""
    models_to_try = [GEMINI_MODEL]

    # Optional fallback model from Vercel environment variables.
    fallback_model = os.getenv(
        "GEMINI_FALLBACK_MODEL", "gemini-2.5-flash"
    ).strip()

    if fallback_model and fallback_model not in models_to_try:
        models_to_try.append(fallback_model)

    last_error = None

    for model_name in models_to_try:
        for attempt in range(3):
            try:
                result = gemini_client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={"response_mime_type": "application/json"}
                )
                return json.loads(result.text)

            except errors.APIError as exc:
                last_error = exc
                code = getattr(exc, "code", None)

                # Retry temporary overloads and rate limits.
                if code not in (429, 500, 502, 503, 504):
                    raise

                if attempt < 2:
                    time.sleep(2 ** (attempt + 1))

    raise last_error


def extract_request(text, state):
    today = date.today().isoformat()

    prompt = f"""
You extract hotel booking details from user speech.

Today's date: {today}
Current booking context: {json.dumps(state, default=str)}

User said: {text}

Return ONLY valid JSON with these keys:
{{
  "intent": "hotel_search | general",
  "hotel_name": null,
  "check_in": null,
  "check_out": null,
  "guests": 1,
  "message": null
}}

Rules:
- Use ISO dates YYYY-MM-DD.
- Resolve relative dates using today's date.
- If a date is unclear, return null for it.
- Never invent hotel availability or booking confirmation.
- If the user is asking about hotels or rooms, use hotel_search.
- If the user asks a general question, use general.
- Preserve existing hotel and date details from the context when relevant.
- Do not claim that a booking has already been made.
"""
    data = gemini_json(prompt)

    if not isinstance(data, dict):
        return {"intent": "general"}

    return data


def find_available_rooms(hotel_name, check_in, check_out):
    start = date.fromisoformat(str(check_in))
    end = date.fromisoformat(str(check_out))

    if end <= start:
        raise ValueError("Check-out must be after check-in.")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                r.id AS room_id,
                h.id AS hotel_id,
                h.name AS hotel_name,
                h.location,
                r.room_number,
                r.room_type,
                r.price_per_night
            FROM rooms r
            JOIN hotels h ON h.id = r.hotel_id
            WHERE h.name LIKE %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM bookings b
                  WHERE b.room_id = r.id
                    AND b.status = 'confirmed'
                    AND b.check_in < %s
                    AND b.check_out > %s
              )
            ORDER BY r.price_per_night
            """,
            (f"%{hotel_name}%", end, start)
        )

        rooms = cursor.fetchall()

        # Return JSON-friendly values.
        for room in rooms:
            room["price_per_night"] = float(room["price_per_night"])

        return rooms
    finally:
        cursor.close()
        conn.close()


def create_guest(name):
    """Create a guest record for a new booking."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT INTO users (name) VALUES (%s)",
            (name,)
        )
        conn.commit()
        return cursor.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def reserve_room(user_id, room_id, check_in, check_out):
    """Recheck availability and save the booking transactionally."""
    start = date.fromisoformat(str(check_in))
    end = date.fromisoformat(str(check_out))

    if end <= start:
        raise ValueError("Invalid booking dates.")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        conn.start_transaction()

        # Serialize booking attempts for the same room.
        cursor.execute(
            "SELECT id FROM rooms WHERE id = %s FOR UPDATE",
            (room_id,)
        )

        if not cursor.fetchone():
            conn.rollback()
            return {"success": False, "message": "Room not found."}

        cursor.execute(
            """
            SELECT id
            FROM bookings
            WHERE room_id = %s
              AND status = 'confirmed'
              AND check_in < %s
              AND check_out > %s
            LIMIT 1
            """,
            (room_id, end, start)
        )

        if cursor.fetchone():
            conn.rollback()
            return {
                "success": False,
                "message": "Sorry, this room has just been booked."
            }

        cursor.execute(
            "SELECT id FROM users WHERE id = %s",
            (user_id,)
        )

        if not cursor.fetchone():
            conn.rollback()
            return {"success": False, "message": "Guest not found."}

        cursor.execute(
            """
            INSERT INTO bookings
                (user_id, room_id, check_in, check_out, status)
            VALUES (%s, %s, %s, %s, 'confirmed')
            """,
            (user_id, room_id, start, end)
        )

        booking_id = cursor.lastrowid
        conn.commit()

        return {
            "success": True,
            "booking_id": booking_id
        }

    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def build_room_list(rooms):
    lines = []
    for index, room in enumerate(rooms, start=1):
        lines.append(
            f"Option {index}: {room['room_type']}, "
            f"room {room['room_number']}, "
            f"Rs. {room['price_per_night']:.2f} per night."
        )
    return "\n".join(lines)


def select_room(text, rooms):
    """Match a spoken room number, option number, or room type."""
    normalized = text.strip().lower()

    if not rooms:
        return None

    # Examples: "option 2", "room 1", "second one".
    import re

    match = re.search(
        r"\b(?:option|room|number|no\.?)\s*(\d+)\b",
        normalized
    )

    if match:
        number = int(match.group(1))
        if 1 <= number <= len(rooms):
            return rooms[number - 1]

    words_to_numbers = {
        "first": 1, "one": 1, "pehla": 1, "पहला": 1,
        "second": 2, "two": 2, "doosra": 2, "दूसरा": 2,
        "third": 3, "three": 3, "teesra": 3, "तीसरा": 3,
        "fourth": 4, "four": 4
    }

    for word, number in words_to_numbers.items():
        if word in normalized and number <= len(rooms):
            return rooms[number - 1]

    # Match a specific room type when the user says it.
    matches = [
        room for room in rooms
        if room["room_type"].lower() in normalized
    ]

    if len(matches) == 1:
        return matches[0]

    return None


def process_booking(text, state):
    """Handle booking conversation turns."""

    stage = state.get("stage")

    if stage == "awaiting_room":
        room = select_room(text, state["rooms"])

        if not room:
            return (
                "Please tell me the option number or room type "
                "you want to book.",
                None
            )

        state["selected_room"] = room
        state["stage"] = "awaiting_name"

        return (
            f"You selected {room['room_type']}, room "
            f"{room['room_number']}, at Rs. "
            f"{room['price_per_night']:.2f} per night. "
            "Please tell me the guest name for the booking.",
            None
        )

    if stage == "awaiting_name":
        name = text.strip()

        if len(name) < 2 or len(name) > 100:
            return "Please tell me a valid guest name.", None

        state["guest_name"] = name
        state["stage"] = "awaiting_confirmation"

        room = state["selected_room"]

        return (
            f"Please confirm: {state['hotel_name']}, "
            f"{room['room_type']}, check-in {state['check_in']}, "
            f"check-out {state['check_out']}, guest {name}. "
            "Should I confirm this booking? Say yes or no.",
            None
        )

    if stage == "awaiting_confirmation":
        normalized = text.strip().lower()

        yes_words = {"yes", "yes book", "confirm", "haan", "han",
                     "ha", "kar do", "book it", "ji haan"}
        no_words = {"no", "cancel", "nahi", "nahin", "mat karo"}

        if normalized in no_words or normalized.startswith("no "):
            state.clear()
            return "Okay, I have not made the booking.", None

        if normalized not in yes_words:
            return "Please say yes to confirm or no to cancel.", None

        try:
            user_id = create_guest(state["guest_name"])

            result = reserve_room(
                user_id,
                state["selected_room"]["room_id"],
                state["check_in"],
                state["check_out"]
            )

            if not result["success"]:
                state.clear()
                return result["message"], None

            booking_id = result["booking_id"]
            state.clear()

            return (
                f"Your booking is confirmed. Your booking ID is "
                f"{booking_id}. Thank you!",
                {"booking_id": booking_id}
            )

        except Exception:
            # Do not tell the user a booking succeeded on failure.
            print("Booking operation failed.")
            return (
                "I could not complete the booking. "
                "Please try again or contact the hotel.",
                None
            )

    # New hotel search request.
    data = extract_request(text, state)

    if data.get("intent") != "hotel_search":
        reply = data.get("message") or (
            "Hello! I can help you search for hotels and book rooms."
        )
        return str(reply), None

    hotel_name = data.get("hotel_name") or state.get("hotel_name")
    check_in = data.get("check_in") or state.get("check_in")
    check_out = data.get("check_out") or state.get("check_out")

    if not hotel_name:
        state.clear()
        return "Which hotel's room would you like to book?", None

    state["hotel_name"] = str(hotel_name)

    if not check_in or not check_out:
        state["check_in"] = check_in
        state["check_out"] = check_out
        state["stage"] = "awaiting_dates"
        return (
            f"What are your check-in and check-out dates "
            f"for {hotel_name}?",
            None
        )

    try:
        rooms = find_available_rooms(hotel_name, check_in, check_out)
    except ValueError as exc:
        return str(exc), None

    if not rooms:
        state.clear()
        return (
            f"Sorry, no available rooms were found at {hotel_name} "
            f"between {check_in} and {check_out}.",
            None
        )

    state.update({
        "hotel_name": hotel_name,
        "check_in": str(check_in),
        "check_out": str(check_out),
        "rooms": rooms,
        "stage": "awaiting_room"
    })

    return (
        f"I found {len(rooms)} available rooms at {hotel_name}. "
        f"{build_room_list(rooms)} "
        "Please say the option number or room type you prefer.",
        None
    )


@app.post("/api/voice")
async def voice_assistant(
    audio: UploadFile = File(...),
    conversation_id: str = Form("default")
):
    if not eleven:
        raise HTTPException(
            status_code=500,
            detail="ELEVENLABS_API_KEY is missing."
        )

    if not gemini_client:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY is missing."
        )

    raw_audio = await audio.read()

    if not raw_audio:
        raise HTTPException(status_code=400, detail="Audio is empty.")

    if len(raw_audio) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio file too large.")

    try:
        transcription = eleven.speech_to_text.convert(
            file=io.BytesIO(raw_audio),
            model_id="scribe_v1"
        )

        user_text = (getattr(transcription, "text", "") or "").strip()

        if not user_text:
            raise HTTPException(
                status_code=400,
                detail="Speech could not be understood."
            )

        state = sessions.setdefault(conversation_id, {})

        # If we're waiting for dates, extract them using Gemini.
        if state.get("stage") == "awaiting_dates":
            data = extract_request(user_text, state)

            state["check_in"] = data.get("check_in")
            state["check_out"] = data.get("check_out")

            if not state["check_in"] or not state["check_out"]:
                reply = (
                    "Please provide both check-in and check-out dates, "
                    "for example, 25 October to 26 October."
                )
            else:
                reply, _ = process_booking(user_text, state)
        else:
            reply, _ = process_booking(user_text, state)

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
                detail="ElevenLabs did not return audio."
            )

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
        print("Voice assistant error:", repr(exc))
        raise HTTPException(
            status_code=502,
            detail="Voice request failed. Check the terminal."
        )
