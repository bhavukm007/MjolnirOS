const TARGET_SAMPLE_RATE = 16000;

const base64 = (buffer) => {
  const bytes = new Uint8Array(buffer);
  let value = "";
  bytes.forEach((byte) => { value += String.fromCharCode(byte); });
  return btoa(value);
};

function pcm16(samples, sampleRate) {
  const ratio = sampleRate / TARGET_SAMPLE_RATE;
  const result = new Int16Array(Math.floor(samples.length / ratio));
  for (let index = 0; index < result.length; index += 1) {
    const start = Math.floor(index * ratio);
    const end = Math.min(Math.floor((index + 1) * ratio), samples.length);
    let total = 0;
    for (let cursor = start; cursor < end; cursor += 1) total += samples[cursor];
    result[index] = Math.max(-1, Math.min(1, total / Math.max(1, end - start))) * 0x7fff;
  }
  return result.buffer;
}

/** Browser microphone bridge for the backend's continuous Vosk session. */
export class VoiceRuntime {
  constructor({ apiBaseUrl, onCommand, onState, onInterruption }) {
    Object.assign(this, { apiBaseUrl, onCommand, onState, onInterruption, sessionId: null, stream: null, audioContext: null, processor: null, chain: Promise.resolve(), interrupted: false });
  }
  async start() {
    const session = await this.request("/voice/sessions", { method: "POST" });
    this.sessionId = session.session_id;
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    this.audioContext = new AudioContext();
    const source = this.audioContext.createMediaStreamSource(this.stream);
    this.processor = this.audioContext.createScriptProcessor(4096, 1, 1);
    this.processor.onaudioprocess = ({ inputBuffer }) => this.process(inputBuffer.getChannelData(0));
    source.connect(this.processor); const muted = this.audioContext.createGain(); muted.gain.value = 0; this.processor.connect(muted); muted.connect(this.audioContext.destination);
    this.onState("Listening for Mjolnir");
  }
  async stop() {
    const id = this.sessionId; this.sessionId = null; this.processor?.disconnect(); await this.audioContext?.close(); this.stream?.getTracks().forEach((track) => track.stop());
    if (id) try { await this.request(`/voice/sessions/${id}`, { method: "DELETE" }); } catch { /* backend stopped first */ }
    this.onState("Voice listening is off");
  }
  process(samples) {
    if (!this.sessionId) return;
    if (Math.max(...samples.map(Math.abs)) > 0.08 && !this.interrupted) { this.interrupted = true; this.onInterruption(); window.setTimeout(() => { this.interrupted = false; }, 700); }
    const audio_base64 = base64(pcm16(samples, this.audioContext.sampleRate));
    this.chain = this.chain.then(async () => {
      if (!this.sessionId) return;
      const result = await this.request(`/voice/sessions/${this.sessionId}/audio`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ audio_base64 }) });
      if (result.command) this.onCommand(result.command);
    }).catch(() => this.onState("Voice connection lost"));
  }
  async request(path, options) { const response = await fetch(`${this.apiBaseUrl}${path}`, options); const body = await response.json(); if (!response.ok || !body.success) throw new Error(body.detail ?? body.message); return body.data; }
}
