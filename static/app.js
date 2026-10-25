
const mic = document.getElementById("mic");
const statusText = document.getElementById("status");
const messages = document.getElementById("messages");

let recorder = null;
let stream = null;
let chunks = [];
let busy = false;
let startedAt = 0;
let maxTimer = null;

function setStatus(text) {
  statusText.textContent = text;
}

function addMessage(text, role) {
  const div = document.createElement("div");
  div.className = `message ${role}`;
  div.textContent = text;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

function releaseMic() {
  if (maxTimer) clearTimeout(maxTimer);
  maxTimer = null;
  if (stream) stream.getTracks().forEach(track => track.stop());
  stream = null;
  recorder = null;
  mic.disabled = false;
  mic.classList.remove("recording");
  mic.textContent = "🎙️";
}

async function sendAudio(blob) {
  if (!blob.size) {
    setStatus("Audio record nahi hui. Dobara try karein.");
    releaseMic();
    busy = false;
    return;
  }

  busy = true;
  mic.disabled = true;
  setStatus("Aapki baat samajh raha hoon...");

  try {
    const form = new FormData();
    form.append("audio", blob, "recording.webm");

    const response = await fetch("/api/voice", {
      method: "POST",
      body: form
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Voice request fail hui.");
    }

    if (data.transcript) addMessage(data.transcript, "user");
    if (data.reply) addMessage(data.reply, "assistant");

    if (data.audio_base64) {
      setStatus("Assistant bol raha hai...");
      const audio = new Audio(
        `data:${data.audio_mime_type || "audio/mpeg"};base64,${data.audio_base64}`
      );
      await audio.play();
      await new Promise(resolve => {
        audio.onended = resolve;
        audio.onerror = resolve;
      });
    }

    setStatus("Taiyaar! Agli baat ke liye mic dabayein.");
  } catch (error) {
    console.error(error);
    setStatus(`Error: ${error.message}`);
  } finally {
    releaseMic();
    busy = false;
  }
}

function stopRecording() {
  if (!recorder || recorder.state !== "recording") return;

  if (Date.now() - startedAt < 800) {
    setStatus("Thoda aur boliye, phir mic dabayein.");
    return;
  }

  if (maxTimer) clearTimeout(maxTimer);
  maxTimer = null;
  recorder.stop();
  setStatus("Recording complete ho rahi hai...");
}

mic.addEventListener("click", async () => {
  if (busy) return;

  if (recorder?.state === "recording") {
    stopRecording();
    return;
  }

  try {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      throw new Error("Is browser mein microphone recording supported nahi hai.");
    }

    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    chunks = [];

    const supportedType = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/mp4"
    ].find(type => MediaRecorder.isTypeSupported(type));

    recorder = supportedType
      ? new MediaRecorder(stream, { mimeType: supportedType })
      : new MediaRecorder(stream);

    recorder.ondataavailable = event => {
      if (event.data.size > 0) chunks.push(event.data);
    };


    recorder.onerror = () => {
        setStatus("Recording mein problem hui. Dobara try karein.");
        releaseMic();
        busy = false;
      };

    recorder.onstop = () => {
      const blob = new Blob(chunks, {
        type: recorder?.mimeType || "audio/webm"
      });
      releaseMic();
      sendAudio(blob);
    };

    recorder.start();
    startedAt = Date.now();
    mic.classList.add("recording");
    mic.textContent = "⏹️";
    setStatus("Sun raha hoon... bolne ke baad mic dobara dabayein.");

    maxTimer = setTimeout(() => {
      if (recorder?.state === "recording") stopRecording();
    }, 15000);

  } catch (error) {
    console.error(error);
    releaseMic();
    setStatus(`Mic access nahi mila: ${error.message}`);
  }
});
