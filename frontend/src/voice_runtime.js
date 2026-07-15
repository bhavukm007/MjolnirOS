import { voiceLog, voiceState } from "./voice_logger.js";

const TARGET_SAMPLE_RATE = 16000;

class VoiceTransportError extends Error {
  constructor(message, { path, method, status = null, responseBody = "", cause } = {}) {
    super(message, { cause });
    this.name = "VoiceTransportError";
    this.path = path;
    this.method = method;
    this.status = status;
    this.responseBody = responseBody;
  }
}

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
  constructor({ apiBaseUrl, onCommand, onWake, onState, onInterruption, onAmplitude, onVoiceState }) {
    Object.assign(this, { apiBaseUrl, onCommand, onWake, onState, onInterruption, onAmplitude, onVoiceState, sessionId: null, stream: null, mediaRecorder: null, audioContext: null, source: null, processor: null, mutedOutput: null, chain: Promise.resolve(), releasePromise: null, interrupted: false, capturePaused: false, playbackCount: 0, manuallyPaused: false, pipelineBusy: false, resumeVoiceState: "WAITING_FOR_WAKE", audioGeneration: 0, frameCount: 0, lastDebugAt: 0, voiceState: "IDLE" });
  }
  get sessionActive() { return Boolean(this.sessionId); }
  get paused() { return this.manuallyPaused; }
  get listeningEnabled() { return this.sessionActive && !this.paused; }
  async start() {
    if (this.sessionId) return;
    const previous = window.__mjolnirVoiceRuntime;
    if (previous && previous !== this) await previous.stop();
    window.__mjolnirVoiceRuntime = this;
    this.capturePaused = true;
    voiceLog("DEBUG", "voice_connection_attempt", { transport: "rest" });
    const session = await this.request("/voice/sessions", { method: "POST" });
    this.sessionId = session.session_id;
    voiceLog("DEBUG", "voice_connection_connected", { transport: "rest", session_id: this.sessionId });
    voiceLog("INFO", "voice_session_created", { session_id: this.sessionId });
    try {
      this.transition("WAITING_FOR_WAKE");
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, sampleRate: TARGET_SAMPLE_RATE, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      this.audioContext = new AudioContext();
      await this.audioContext.resume();
    } catch (error) {
      voiceLog("ERROR", "voice_microphone_failure", { error: error.message });
      await this.releaseResources("startup_failure");
      throw error;
    }
    voiceLog("INFO", "voice_microphone_resumed", {
      track: this.stream.getAudioTracks()[0]?.label,
      audioContext: this.audioContext.state,
      sampleRate: this.audioContext.sampleRate
    });
    this.source = this.audioContext.createMediaStreamSource(this.stream);
    this.processor = this.audioContext.createScriptProcessor(4096, 1, 1);
    this.processor.onaudioprocess = ({ inputBuffer }) => this.process(inputBuffer.getChannelData(0));
    this.source.connect(this.processor); this.mutedOutput = this.audioContext.createGain(); this.mutedOutput.gain.value = 0; this.processor.connect(this.mutedOutput); this.mutedOutput.connect(this.audioContext.destination);
    this.capturePaused = false;
    this.onState("Listening for Mjolnir");
  }
  async stop() {
    await this.releaseResources("runtime_stopped");
    this.manuallyPaused = false;
    this.transition("IDLE");
    if (window.__mjolnirVoiceRuntime === this) window.__mjolnirVoiceRuntime = null;
    this.onState("Voice listening is off");
  }
  async releaseResources(reason) {
    if (this.releasePromise) return this.releasePromise;
    this.releasePromise = this.releaseResourcesOnce(reason);
    try {
      await this.releasePromise;
    } finally {
      this.releasePromise = null;
    }
  }
  async releaseResourcesOnce(reason) {
    const id = this.sessionId;
    const hadStream = Boolean(this.stream);
    const hadAudioContext = Boolean(this.audioContext);
    this.sessionId = null;
    this.audioGeneration += 1;
    this.capturePaused = true;
    this.pipelineBusy = false;
    this.playbackCount = 0;
    this.interrupted = false;
    if (this.mediaRecorder && this.mediaRecorder.state !== "inactive") {
      try { this.mediaRecorder.stop(); } catch (error) { voiceLog("ERROR", "voice_media_recorder_cleanup_failure", { error: error.message }); }
    }
    this.mediaRecorder = null;
    if (this.processor) this.processor.onaudioprocess = null;
    try { this.processor?.disconnect(); } catch {}
    try { this.source?.disconnect(); } catch {}
    try { this.mutedOutput?.disconnect(); } catch {}
    for (const track of this.stream?.getTracks() ?? []) {
      try { track.stop(); } catch (error) { voiceLog("ERROR", "voice_track_cleanup_failure", { error: error.message }); }
    }
    if (this.audioContext && this.audioContext.state !== "closed") {
      try { await this.audioContext.close(); } catch (error) { voiceLog("ERROR", "voice_audio_context_cleanup_failure", { error: error.message }); }
    }
    this.processor = null;
    this.source = null;
    this.mutedOutput = null;
    this.stream = null;
    this.audioContext = null;
    if (id) try { await this.request(`/voice/sessions/${id}`, { method: "DELETE" }); } catch (cleanupError) {
      voiceLog("ERROR", "voice_session_cleanup_failure", { error: cleanupError.message, stack: cleanupError.stack, session_id: id });
    }
    if (id) voiceLog("INFO", "voice_session_destroyed", { session_id: id });
    if (id) voiceLog("DEBUG", "voice_connection_closed", { transport: "rest", reason, session_id: id });
    voiceLog("INFO", "voice_resources_released", { reason, media_stream: hadStream, audio_context: hadAudioContext, recognition_session: Boolean(id) });
  }
  async pause() {
    if (!this.sessionId || this.manuallyPaused) return;
    this.manuallyPaused = true;
    this.resumeVoiceState = "WAITING_FOR_WAKE";
    await this.releaseResources("manual_pause");
    voiceLog("INFO", "voice_microphone_paused", { reason: "manual" });
    this.transition("PAUSED");
    this.onState("Voice listening is off");
  }
  async resume() {
    this.manuallyPaused = false;
    await this.start();
    voiceLog("INFO", "voice_microphone_resumed", { reason: "manual", recreated: true });
  }
  beginPlayback(reason = "tts") {
    this.playbackCount += 1;
    this.capturePaused = true;
    voiceLog("INFO", "voice_microphone_paused", { reason });
  }
  endPlayback(reason = "tts_complete") {
    this.playbackCount = Math.max(0, this.playbackCount - 1);
    this.capturePaused = this.manuallyPaused || this.pipelineBusy || this.playbackCount > 0;
    if (!this.capturePaused) voiceLog("INFO", "voice_microphone_resumed", { reason });
  }
  process(samples) {
    if (!this.sessionId) return;
    if (this.capturePaused) return;
    this.frameCount += 1;
    const peak = Math.max(...samples.map(Math.abs));
    this.onAmplitude?.(peak);
    if (performance.now() - this.lastDebugAt > 1000) {
      this.lastDebugAt = performance.now();
      voiceLog("DEBUG", "voice_audio_packet", { frames: this.frameCount, samples: samples.length, peak });
    }
    if (this.playbackCount > 0 && peak > 0.08 && !this.interrupted) { this.interrupted = true; this.onInterruption(); window.setTimeout(() => { this.interrupted = false; }, 700); }
    const audio_base64 = base64(pcm16(samples, this.audioContext.sampleRate));
    const generation = this.audioGeneration;
    this.chain = this.chain.then(async () => {
      if (!this.sessionId || generation !== this.audioGeneration) return;
      voiceLog("DEBUG", "voice_audio_packet_sent", { bytes: Math.floor(audio_base64.length * 3 / 4), frame: this.frameCount, session_id: this.sessionId });
      const result = await this.request(`/voice/sessions/${this.sessionId}/audio`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ audio_base64 }) });
      if (result.transcript) voiceLog("DEBUG", "voice_vosk_transcript", { transcript: result.transcript });
      if (result.state === "listening_for_wake_word" && this.voiceState === "LISTENING_FOR_COMMAND") {
        this.audioGeneration += 1;
        this.resumeVoiceState = "WAITING_FOR_WAKE";
        this.transition("FOLLOW_UP_WINDOW_END", { reason: "timeout" });
        voiceLog("INFO", "voice_follow_up_timeout");
        this.transition("RETURN_TO_WAKE");
        this.transition("WAITING_FOR_WAKE");
        this.onState("Listening for Mjolnir");
        return;
      }
      if (result.wake_word_detected) {
        // Invalidate every queued idle frame. The wake utterance is never
        // eligible to become the command that follows it.
        this.audioGeneration += 1;
        this.transition("WAKE_DETECTED");
        // Pause capture for the actual acknowledgement duration so its speaker
        // audio never enters the command recognizer.
        this.pipelineBusy = true;
        this.capturePaused = true;
        voiceLog("INFO", "voice_microphone_paused", { reason: "tts" });
        this.transition("TTS_START", { utterance: "wake_acknowledgement" });
        this.transition("SPEAKING", { utterance: "wake_acknowledgement" });
        try {
          await this.onWake?.();
        } catch (error) {
          voiceLog("ERROR", "voice_tts_failure", { error: error.message, utterance: "wake_acknowledgement" });
        } finally {
          this.transition("TTS_END", { utterance: "wake_acknowledgement" });
          this.pipelineBusy = false;
          this.capturePaused = this.manuallyPaused;
          if (!this.capturePaused) voiceLog("INFO", "voice_microphone_resumed", { reason: "tts_complete" });
          this.showCommandListening();
        }
      }
      if (result.command) {
        // Discard the command tail and stop queue growth while planner, tool,
        // and response TTS processing own the session.
        this.audioGeneration += 1;
        this.pipelineBusy = true;
        this.capturePaused = true;
        voiceLog("INFO", "voice_microphone_paused", { reason: "processing" });
        this.transition("PROCESSING", { command: result.command });
        voiceLog("INFO", "voice_command_dispatch", { command: result.command });
        const commandSessionId = this.sessionId;
        let commandError = null;
        try {
          await this.onCommand(result.command, (event, detail = {}) => this.handlePipelineEvent(event, detail));
        } catch (error) {
          commandError = error;
          voiceLog("ERROR", "voice_command_pipeline_failure", { error: error.message, stack: error.stack });
        } finally {
          try {
            if (this.sessionId === commandSessionId) {
              await this.request(`/voice/sessions/${commandSessionId}/complete`, { method: "POST" });
            }
          } finally {
            this.pipelineBusy = false;
            this.capturePaused = this.manuallyPaused;
          }
        }
        if (this.manuallyPaused || !this.sessionId) {
          this.transition("PAUSED");
          this.onState("Voice listening is off");
          return;
        }
        if (!this.capturePaused) voiceLog("INFO", "voice_microphone_resumed", { reason: "processing_complete" });
        this.resumeVoiceState = "WAITING_FOR_WAKE";
        this.transition("RETURN_TO_WAKE");
        this.transition("WAITING_FOR_WAKE");
        this.onState("Listening for Mjolnir");
        if (commandError) voiceLog("INFO", "voice_command_failure_returned_to_wake", { error: commandError.message });
      }
    }).catch(async (error) => {
      voiceLog("ERROR", "voice_connection_closed", {
        transport: "rest",
        close_code: error.status,
        close_reason: error.message,
        path: error.path,
        method: error.method,
        response_body: error.responseBody,
        stack: error.stack
      });
      if (error.status === 404 && error.path?.startsWith("/voice/sessions/")) {
        try {
          await this.reconnectSession(error);
          return;
        } catch (reconnectError) {
          voiceLog("ERROR", "voice_reconnect_failure", {
            error: reconnectError.message,
            stack: reconnectError.stack,
            status: reconnectError.status
          });
          error = reconnectError;
        }
      }
      voiceLog("ERROR", "voice_runtime_failure", { error: error.message, stack: error.stack });
      this.onState("Voice connection lost");
    });
  }
  async reconnectSession(error) {
    const staleSessionId = this.sessionId;
    if (!staleSessionId) return;
    voiceLog("DEBUG", "voice_reconnect_attempt", {
      transport: "rest",
      reason: error.message,
      status: error.status,
      stale_session_id: staleSessionId
    });
    this.audioGeneration += 1;
    const session = await this.request("/voice/sessions", { method: "POST" });
    if (this.sessionId !== staleSessionId) {
      try {
        await this.request(`/voice/sessions/${session.session_id}`, { method: "DELETE" });
      } catch (cleanupError) {
        voiceLog("ERROR", "voice_session_cleanup_failure", {
          error: cleanupError.message,
          stack: cleanupError.stack,
          session_id: session.session_id
        });
      }
      return;
    }
    this.sessionId = session.session_id;
    this.interrupted = false;
    this.pipelineBusy = false;
    this.capturePaused = this.manuallyPaused;
    this.resumeVoiceState = "WAITING_FOR_WAKE";
    voiceLog("DEBUG", "voice_reconnect_success", {
      transport: "rest",
      stale_session_id: staleSessionId,
      session_id: this.sessionId
    });
    if (this.manuallyPaused) {
      this.transition("PAUSED");
      this.onState("Voice listening is off");
      return;
    }
    this.transition("WAITING_FOR_WAKE");
    this.onState("Listening for Mjolnir");
  }
  transition(state, detail = {}) {
    this.voiceState = state;
    this.onVoiceState?.(state, detail);
    voiceState(state, detail);
  }
  handlePipelineEvent(event, detail = {}) {
    if (event === "TOOL_COMPLETION") voiceLog("INFO", "voice_tool_completion", detail);
    else if (event === "TTS_FAILURE") voiceLog("ERROR", "voice_tts_failure", detail);
    else if (event === "TTS_START") {
      this.transition("TTS_START", detail);
      this.transition("SPEAKING", detail);
    }
    else if (event === "TTS_END") this.transition(event, detail);
    else voiceLog("INFO", event, detail);
  }
  showCommandListening() {
    this.resumeVoiceState = "LISTENING_FOR_COMMAND";
    if (this.manuallyPaused) {
      this.transition("PAUSED");
      this.onState("Voice listening is off");
      return;
    }
    this.transition("LISTENING_FOR_COMMAND");
    this.onState("Listening for your command");
  }
  async request(path, options = {}) {
    const method = options.method ?? "GET";
    voiceLog("DEBUG", "voice_transport_request", { transport: "rest", method, path, session_id: this.sessionId });
    let response;
    try {
      response = await fetch(`${this.apiBaseUrl}${path}`, options);
    } catch (error) {
      throw new VoiceTransportError(`Voice request failed: ${error.message}`, { path, method, cause: error });
    }
    const responseBody = await response.text();
    voiceLog("DEBUG", "voice_transport_response", { transport: "rest", method, path, status: response.status, session_id: this.sessionId });
    let body;
    try {
      body = JSON.parse(responseBody);
    } catch (error) {
      throw new VoiceTransportError("Voice endpoint returned invalid JSON.", { path, method, status: response.status, responseBody, cause: error });
    }
    if (!response.ok || !body.success) {
      throw new VoiceTransportError(body.detail ?? body.message ?? `Voice request failed with status ${response.status}.`, { path, method, status: response.status, responseBody });
    }
    return body.data;
  }
}
