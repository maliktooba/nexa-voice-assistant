"""
api/index.py — Flask backend for Vercel deployment.

STT: Groq Whisper (reliable, auto-detects English/Urdu).
TTS: English uses the browser's speechSynthesis (fast, works
everywhere). Urdu is generated server-side with gTTS and sent back
as audio bytes, because most Windows/Chrome setups don't have an
Urdu voice installed, so the browser's own TTS stays silent for Urdu.
"""

import os
import io
import json
import base64
import traceback
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from groq import Groq
from gtts import gTTS

load_dotenv()

app = Flask(
    __name__,
    template_folder="../templates",
    static_folder="../static",
)

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = (
    "You are Nexa, a friendly and warm AI voice assistant. You remember "
    "the conversation so far, so refer back to earlier context naturally "
    "when relevant. "
    "\n\n"
    "The user's message may arrive in plain English, Roman Urdu (Urdu "
    "words spelled in English letters, e.g. 'ap kesy hain'), or actual "
    "Urdu script (e.g. 'آپ کیسے ہیں'). "
    "\n\n"
    "STRICT LANGUAGE MATCHING: reply in EXACTLY the same language as "
    "the user's message. If English, reply in plain English only — "
    "never default to Urdu greetings. If Urdu (script or Roman), reply "
    "in Roman Urdu. "
    "\n\n"
    "Respond ONLY with a valid JSON object (no markdown, no code "
    "fences, no extra text) with exactly FOUR keys: "
    "\"user_message_roman\", \"reply\", \"reply_speech\", \"reply_lang\". "
    "\n\n"
    "CRITICAL FORMAT RULE: \"user_message_roman\" and \"reply\" must "
    "ALWAYS be written in ROMAN LETTERS (English alphabet) — even when "
    "the language is Urdu. NEVER put Urdu/Arabic script (اردو رسم "
    "الخط) in these two fields, no matter how long or complex the "
    "reply is. Only \"reply_speech\" may contain real Urdu script, and "
    "ONLY when reply_lang is \"ur\" — this field exists purely so the "
    "text-to-speech engine can pronounce it correctly; the person "
    "reading the screen never sees this field.\n"
    "\n"
    "EXAMPLE 1 (English input):\n"
    "User: \"hello, how are you\"\n"
    "Output: {\"user_message_roman\": \"hello, how are you\", "
    "\"reply\": \"Hello! I'm doing great, how can I help you today?\", "
    "\"reply_speech\": \"Hello! I'm doing great, how can I help you today?\", "
    "\"reply_lang\": \"en\"}\n"
    "\n"
    "EXAMPLE 2 (Urdu input, spoken or in Urdu script):\n"
    "User: \"مجھے اچھی جگہ بتائیں\"\n"
    "Output: {\"user_message_roman\": \"Mujhe achi jagah batayen\", "
    "\"reply\": \"Aap Islamabad ya Murree ja sakte hain, dono khubsurat "
    "jagah hain.\", "
    "\"reply_speech\": \"آپ اسلام آباد یا مری جا سکتے ہیں، دونوں خوبصورت "
    "جگہ ہیں۔\", "
    "\"reply_lang\": \"ur\"}\n"
    "\n"
    "Notice in EXAMPLE 2 that \"reply\" is in Roman letters (readable "
    "English alphabet) while \"reply_speech\" is in real Urdu script — "
    "always follow this exact pattern, even for long answers with "
    "lists or multiple points. "
    "\n\n"
    "All text must be plain spoken sentences — no markdown, no tables, "
    "no headers, no bullet symbols, no bold. Be direct and brief for "
    "simple questions (2-4 sentences), but give the FULL answer for "
    "recipes, steps, or instructions — never cut off partway."
)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/chat', methods=['POST'])
def chat():
    def error_response(msg):
        return jsonify({
            "user_message_roman": "",
            "reply": msg,
            "reply_speech": msg,
            "reply_lang": "en",
            "audio_b64": None
        })

    try:
        audio_file = request.files.get('audio')
        history_raw = request.form.get('history', '[]')
        history = json.loads(history_raw)

        if not audio_file:
            return error_response("Sorry, no audio was received. Please try again.")

        audio_bytes = audio_file.read()

        transcription = client.audio.transcriptions.create(
            file=("recording.webm", audio_bytes),
            model="whisper-large-v3",
        )
        user_text = (transcription.text or "").strip()

        if not user_text:
            return error_response("Sorry, I didn't catch that. Please try again.")

    except Exception as e:
        print(f"⚠️ Transcription error: {e}")
        traceback.print_exc()
        return error_response("Sorry, I had trouble understanding the audio. Please try again.")

    fallback_reply = "Sorry, I ran into an error while thinking about that."

    try:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] \
            + history \
            + [{"role": "user", "content": user_text}]

        completion = client.chat.completions.create(
            messages=messages,
            model="openai/gpt-oss-20b",
        )
        content = completion.choices[0].message.content

        if not content or not content.strip():
            return error_response(fallback_reply)

        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            return error_response(content)

        user_message_roman = parsed.get("user_message_roman", user_text)
        reply = parsed.get("reply", fallback_reply)
        reply_speech = parsed.get("reply_speech", reply)
        reply_lang = parsed.get("reply_lang", "en")

        audio_b64 = None
        if reply_lang == "ur":
            try:
                tts = gTTS(text=reply_speech, lang="ur", slow=False)
                buf = io.BytesIO()
                tts.write_to_fp(buf)
                buf.seek(0)
                audio_b64 = base64.b64encode(buf.read()).decode("utf-8")
            except Exception as tts_err:
                print(f"⚠️ gTTS error: {tts_err}")
                traceback.print_exc()

        return jsonify({
            "user_message_roman": user_message_roman,
            "reply": reply,
            "reply_speech": reply_speech,
            "reply_lang": reply_lang,
            "audio_b64": audio_b64
        })

    except Exception as e:
        print(f"⚠️ LLM API error: {e}")
        traceback.print_exc()
        return error_response(fallback_reply)


if __name__ == '__main__':
    app.run(debug=True, port=5000)