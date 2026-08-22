/*
 * script.js — Browser-based voice pipeline
 * Mic recording: MediaRecorder API.
 * STT: Groq Whisper (server-side).
 * TTS: English via browser speechSynthesis; Urdu via server-generated
 * gTTS audio (browser TTS often has no Urdu voice installed).
 */

const micBtn = document.getElementById('micBtn');
const resetBtn = document.getElementById('resetBtn');
const statusEl = document.getElementById('status');
const userTextEl = document.getElementById('userText');
const aiTextEl = document.getElementById('aiText');

let conversationHistory = [];
let isRecording = false;
let mediaRecorder = null;
let audioChunks = [];
let mediaStream = null;

if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
  statusEl.textContent = "⚠️ Your browser doesn't support microphone access.";
  micBtn.disabled = true;
} else {
  micBtn.addEventListener('click', async () => {
    if (!isRecording) {
      await startRecording();
    } else {
      stopRecording();
    }
  });
}

async function startRecording() {
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    console.error("Mic permission error:", err);
    statusEl.textContent = "⚠️ Mic permission denied. Please allow mic access.";
    return;
  }

  audioChunks = [];
  mediaRecorder = new MediaRecorder(mediaStream);

  mediaRecorder.ondataavailable = (event) => {
    if (event.data.size > 0) audioChunks.push(event.data);
  };

  mediaRecorder.start();
  isRecording = true;
  micBtn.textContent = "⏹ Stop & Send";
  micBtn.classList.add('listening');
  statusEl.textContent = "🎤 Recording... speak now, pause freely";
}

function stopRecording() {
  isRecording = false;
  micBtn.disabled = true;
  micBtn.textContent = "🤔 Thinking...";
  micBtn.classList.remove('listening');
  statusEl.textContent = "🤔 Processing your question...";

  mediaRecorder.onstop = async () => {
    mediaStream.getTracks().forEach(track => track.stop());
    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
    await sendToNexa(audioBlob);

    micBtn.textContent = "🎤 Start Recording";
    micBtn.disabled = false;
  };

  mediaRecorder.stop();
}

async function sendToNexa(audioBlob) {
  try {
    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');
    formData.append('history', JSON.stringify(conversationHistory));

    const response = await fetch('/api/chat', {
      method: 'POST',
      body: formData
    });
    const data = await response.json();

    userTextEl.textContent = data.user_message_roman || "(no input detected)";
    aiTextEl.textContent = data.reply;

    if (data.user_message_roman) {
      conversationHistory.push({ role: "user", content: data.user_message_roman });
      conversationHistory.push({ role: "assistant", content: data.reply });
      if (conversationHistory.length > 20) {
        conversationHistory = conversationHistory.slice(-20);
      }
    }

    statusEl.textContent = "🔊 Playing response...";
    speakReply(data.reply_speech, data.reply_lang, data.audio_b64);

  } catch (err) {
    console.error(err);
    statusEl.textContent = "Something went wrong. Try again.";
  }
}

function speakReply(text, lang, audioB64) {
  if (lang === "ur" && audioB64) {
    const audio = new Audio(`data:audio/mp3;base64,${audioB64}`);
    audio.onended = () => {
      statusEl.textContent = "Press the button to record your next message";
    };
    audio.onerror = () => {
      statusEl.textContent = "Press the button to record your next message";
    };
    audio.play().catch(() => {
      statusEl.textContent = "Press the button to record your next message";
    });
    return;
  }

  if (!window.speechSynthesis) {
    statusEl.textContent = "Press the button to record your next message";
    return;
  }

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "en-US";

  utterance.onend = () => {
    statusEl.textContent = "Press the button to record your next message";
  };
  utterance.onerror = () => {
    statusEl.textContent = "Press the button to record your next message";
  };

  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}

resetBtn.addEventListener('click', () => {
  conversationHistory = [];
  userTextEl.textContent = "—";
  aiTextEl.textContent = "—";
  statusEl.textContent = "Conversation reset. Press the button to start fresh.";
  window.speechSynthesis.cancel();
});