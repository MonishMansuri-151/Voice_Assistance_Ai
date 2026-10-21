# Voice Assistant AI

## About the Project
Voice Assistant AI is a voice-based assistant that allows users to ask questions by speaking. It converts speech into text, generates a response using Google Gemini AI, and converts the response back into speech.

## Features
- Voice input through a microphone
- Speech-to-text using ElevenLabs
- AI-generated responses using Google Gemini
- Text-to-speech using ElevenLabs
- Simple web interface
- Supports natural conversations

## Technologies Used
- Python
- FastAPI
- HTML, CSS, and JavaScript
- ElevenLabs API
- Google Gemini API

## How It Works
1. The user speaks through the microphone.
2. ElevenLabs converts the audio into text.
3. Google Gemini processes the text and generates a response.
4. ElevenLabs converts the response into speech.
5. The user hears the AI-generated answer.

## Project Structure

```text
VoiceAssistantAI/
├── main.py
├── templates/
│   └── index.html
├── static/
│   └── app.js
├── requirements.txt
└── README.md
```

## Requirements
- Python 3.10 or a compatible version
- A Google Gemini API key
- An ElevenLabs API key
- Internet connection

## Installation and Setup

1. Download or extract the project.
2. Open a terminal in the project folder.
3. Create and activate a Python virtual environment.
4. Install the required packages:

   `pip install -r requirements.txt`

5. Create a `.env` file and add your API credentials and model settings:

   `GEMINI_API_KEY=your_gemini_api_key`

   `GEMINI_MODEL=gemini-3.6-flash`

   `ELEVENLABS_API_KEY=your_elevenlabs_api_key`

   `ELEVENLABS_VOICE_ID=your_elevenlabs_voice_id`

6. Start the application:

   `uvicorn main:app --reload`

7. Open `http://127.0.0.1:8000` in your web browser.

## Security
Never share your real API keys or upload your `.env` file publicly. Keep your credentials private.

## Conclusion
This project demonstrates how speech recognition, a large language model, and speech synthesis can be combined to create a simple AI voice assistant.
