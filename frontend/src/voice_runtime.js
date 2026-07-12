const TARGET_SAMPLE_RATE = 16000;

function toBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function toPcm16(samples, sourceRate) {
  const ratio = sourceRate / TARGET_SAMPLE_RATE;
  const output = new Int16Array(Math.floor(samples.length / ratio));
  for (let index = 0; index < output.length; index += 1) {
    const start = Math.floor(index * ratio);
    const end = Math.min(Math.floor((index + 1) * ratio), samples.length);
    let total = 0;
    for (let offset = start; offset < end; offset += 1) total += samples[offset];
    output[index] = Math.max(-1, Math.min(1, total / Math.max(1, end - start))) * 0x7fff;
  }
  return output.buffer;
}

export class VoiceRuntime {
  constructor({ apiBaseUrl, onCommand, onState, onInterruption }) {
    this.apiBaseUrl = apiBaseUrl;
    this.onCommand = onCommand;
    this.onState = onState;
    this.onInterruption = onInterruption;
    this.audioContext = null;
    this.processor = null;
    this.stream = null;
    this.sessionId = null;
    this.sendChain = Promise.resolve();
    this.interrupted = false;
  }

  async start() {
    const session = await this._request("/voice/sessions", { method: "POST" });
    this.sessionId = session.session_id;
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    this.audioContext = new AudioContext();
    const source = this.audioContext.createMediaStreamSource(this.stream);
    this.processor = this.audioContext.createScriptProcessor(4096, 1, 1);
    this.processor.onaudioprocess = (event) => this._processAudio(event.inputBuffer.getChannelData(0));
    source.connect(this.processor);
    const mutedOutput = this.audioContext.createGain();
    mutedOutput.gain.value = 0;
    this.processor.connect(mutedOutput);
    mutedOutput.connect(this.audioContext.destination);
    this.onState("Listening for “Mjolnir”");
  }

  async stop() {
    const sessionId = this.sessionId;
    this.sessionId = null;
    this.processor?.disconnect();
    this.audioContext?.close();
    this.stream?.getTracks().forEach((track) => track.stop());
    this.processor = null;
    this.audioContext = null;
    this.stream = null;
    if (sessionId) {
      try { await this._request(`/voice/sessions/${sessionId}`, { method: "DELETE" }); } catch { /* session may already be closed */ }
    }
    this.onState("Voice listening is off");
  }

  _processAudio(samples) {
    if (!this.sessionId) return;
    const level = Math.max(...samples.map(Math.abs));
    if (level > 0.08 && !this.interrupted) {
      this.interrupted = true;
      this.onInterruption();
      window.setTimeout(() => { this.interrupted = false; }, 700);
    }
    const audioBase64 = toBase64(toPcm16(samples, this.audioContext.sampleRate));
    this.sendChain = this.sendChain.then(async () => {
      if (!this.sessionId) return;
      const result = await this._request(`/voice/sessions/${this.sessionId}/audio`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ audio_base64: audioBase64 })
      });
      if (result.wake_word_detected) this.onState(result.command ? "Command detected" : "Listening for your command");
      if (result.command) {
        this.onState("Listening for “Mjolnir”");
        this.onCommand(result.command);
      }
    }).catch(() => this.onState("Voice connection lost"));
  }

  async _request(path, options) {
    const response = await fetch(`${this.apiBaseUrl}${path}`, options);
    const body = await response.json();
    if (!response.ok || !body.success) throw new Error(body.detail ?? body.message ?? "Voice request failed.");
    return body.data;
  }
}
