import { describe, expect, test, vi } from "vitest";

import { VoiceRuntime } from "./voice_runtime.js";

const samples = () => new Float32Array(256);

describe("VoiceRuntime", () => {
  test("keeps microphone capture paused until overlapping playback completes", () => {
    const runtime = new VoiceRuntime({
      apiBaseUrl: "/api/v1",
      onCommand: vi.fn(),
      onWake: vi.fn(),
      onState: vi.fn(),
      onInterruption: vi.fn()
    });

    runtime.beginPlayback("first");
    runtime.beginPlayback("second");
    runtime.endPlayback("first_complete");

    expect(runtime.capturePaused).toBe(true);
    expect(runtime.playbackCount).toBe(1);

    runtime.endPlayback("second_complete");

    expect(runtime.capturePaused).toBe(false);
    expect(runtime.playbackCount).toBe(0);
  });

  test("returns to wake mode after a voice command completes", async () => {
    const info = vi.spyOn(console, "info").mockImplementation(() => {});
    const onCommand = vi.fn(async (_command, onPhase) => {
      onPhase("TOOL_COMPLETION");
      onPhase("TTS_START");
      onPhase("TTS_END");
    });
    const onState = vi.fn();
    const runtime = new VoiceRuntime({
      apiBaseUrl: "/api/v1",
      onCommand,
      onWake: vi.fn(),
      onState,
      onInterruption: vi.fn()
    });
    runtime.sessionId = "voice-session";
    runtime.audioContext = { sampleRate: 16000 };
    runtime.voiceState = "LISTENING_FOR_COMMAND";
    runtime.request = vi.fn((path) => Promise.resolve(
      path.endsWith("/complete")
        ? { state: "listening_for_wake_word" }
        : { state: "processing_command", command: "open chrome" }
    ));

    runtime.process(samples());
    await runtime.chain;

    expect(onCommand).toHaveBeenCalledWith("open chrome", expect.any(Function));
    expect(runtime.voiceState).toBe("WAITING_FOR_WAKE");
    expect(runtime.capturePaused).toBe(false);
    expect(onState).toHaveBeenLastCalledWith("Listening for Mjolnir");
    const events = info.mock.calls.map(([payload]) => payload.event);
    expect(events).toEqual(expect.arrayContaining([
      "VOICE_STATE: PROCESSING",
      "voice_command_dispatch",
      "voice_tool_completion",
      "VOICE_STATE: TTS_START",
      "VOICE_STATE: TTS_END",
      "VOICE_STATE: RETURN_TO_WAKE",
      "VOICE_STATE: WAITING_FOR_WAKE"
    ]));
    expect(events.indexOf("VOICE_STATE: TTS_START")).toBeLessThan(events.indexOf("VOICE_STATE: TTS_END"));
    const ordered = [
      "VOICE_STATE: PROCESSING",
      "voice_command_dispatch",
      "voice_tool_completion",
      "VOICE_STATE: TTS_START",
      "VOICE_STATE: TTS_END",
      "VOICE_STATE: RETURN_TO_WAKE",
      "VOICE_STATE: WAITING_FOR_WAKE"
    ];
    expect(ordered.map((event) => events.indexOf(event))).toEqual(
      [...ordered.map((event) => events.indexOf(event))].sort((left, right) => left - right)
    );
    info.mockRestore();
  });

  test("inline wake command skips acknowledgement and executes immediately", async () => {
    vi.spyOn(console, "info").mockImplementation(() => {});
    const onWake = vi.fn();
    const onCommand = vi.fn().mockResolvedValue(undefined);
    const runtime = new VoiceRuntime({
      apiBaseUrl: "/api/v1", onCommand, onWake, onState: vi.fn(), onInterruption: vi.fn()
    });
    runtime.sessionId = "voice-session";
    runtime.audioContext = { sampleRate: 16000 };
    runtime.request = vi.fn((path) => Promise.resolve(
      path.endsWith("/complete")
        ? { state: "listening_for_wake_word" }
        : { state: "processing_command", wake_word_detected: true, command: "open chrome" }
    ));

    runtime.process(samples());
    await runtime.chain;

    expect(onWake).not.toHaveBeenCalled();
    expect(onCommand).toHaveBeenCalledWith("open chrome", expect.any(Function));
    expect(runtime.voiceState).toBe("WAITING_FOR_WAKE");
  });

  test("reflects a backend conversation timeout as wake listening", async () => {
    const info = vi.spyOn(console, "info").mockImplementation(() => {});
    const onState = vi.fn();
    const runtime = new VoiceRuntime({
      apiBaseUrl: "/api/v1",
      onCommand: vi.fn(),
      onWake: vi.fn(),
      onState,
      onInterruption: vi.fn()
    });
    runtime.sessionId = "voice-session";
    runtime.audioContext = { sampleRate: 16000 };
    runtime.voiceState = "LISTENING_FOR_COMMAND";
    runtime.request = vi.fn().mockResolvedValue({ state: "listening_for_wake_word" });

    runtime.process(samples());
    await runtime.chain;

    expect(runtime.voiceState).toBe("WAITING_FOR_WAKE");
    expect(onState).toHaveBeenLastCalledWith("Listening for Mjolnir");
    const events = info.mock.calls.map(([payload]) => payload.event);
    expect(events).toEqual([
      "VOICE_STATE: FOLLOW_UP_WINDOW_END",
      "voice_follow_up_timeout",
      "VOICE_STATE: RETURN_TO_WAKE",
      "VOICE_STATE: WAITING_FOR_WAKE"
    ]);
    info.mockRestore();
  });

  test("suppresses audio packet logs at the default INFO level", async () => {
    const debug = vi.spyOn(console, "debug").mockImplementation(() => {});
    const runtime = new VoiceRuntime({
      apiBaseUrl: "/api/v1",
      onCommand: vi.fn(),
      onWake: vi.fn(),
      onState: vi.fn(),
      onInterruption: vi.fn()
    });
    runtime.sessionId = "voice-session";
    runtime.audioContext = { sampleRate: 16000 };
    runtime.request = vi.fn().mockResolvedValue({ state: "listening_for_wake_word" });

    runtime.process(samples());
    await runtime.chain;

    expect(debug).not.toHaveBeenCalled();
    debug.mockRestore();
  });

  test("keeps command listening active when wake TTS fails", async () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    const info = vi.spyOn(console, "info").mockImplementation(() => {});
    const runtime = new VoiceRuntime({
      apiBaseUrl: "/api/v1",
      onCommand: vi.fn(),
      onWake: vi.fn().mockRejectedValue(new Error("speaker unavailable")),
      onState: vi.fn(),
      onInterruption: vi.fn()
    });
    runtime.sessionId = "voice-session";
    runtime.audioContext = { sampleRate: 16000 };
    runtime.request = vi.fn().mockResolvedValue({
      state: "listening_for_command",
      wake_word_detected: true
    });

    runtime.process(samples());
    await runtime.chain;

    const events = info.mock.calls.map(([payload]) => payload.event);
    expect(events.indexOf("VOICE_STATE: TTS_START")).toBeLessThan(events.indexOf("VOICE_STATE: TTS_END"));
    expect(runtime.voiceState).toBe("LISTENING_FOR_COMMAND");
    expect(error).toHaveBeenCalledWith(expect.objectContaining({ event: "voice_tts_failure" }));
    error.mockRestore();
    info.mockRestore();
  });

  test("pause releases every capture resource and resume recreates the runtime", async () => {
    const onState = vi.fn();
    const runtime = new VoiceRuntime({
      apiBaseUrl: "/api/v1",
      onCommand: vi.fn(),
      onWake: vi.fn(),
      onState,
      onInterruption: vi.fn()
    });
    runtime.sessionId = "voice-session";
    runtime.voiceState = "WAITING_FOR_WAKE";
    const track = { stop: vi.fn() };
    runtime.stream = { getTracks: () => [track] };
    runtime.audioContext = { state: "running", close: vi.fn().mockResolvedValue(undefined) };
    runtime.processor = { disconnect: vi.fn(), onaudioprocess: vi.fn() };
    runtime.source = { disconnect: vi.fn() };
    runtime.mutedOutput = { disconnect: vi.fn() };
    runtime.request = vi.fn().mockResolvedValue({ state: "listening_for_wake_word" });

    expect(runtime.sessionActive).toBe(true);
    expect(runtime.paused).toBe(false);
    expect(runtime.listeningEnabled).toBe(true);

    await runtime.pause();

    expect(runtime.sessionActive).toBe(false);
    expect(runtime.paused).toBe(true);
    expect(runtime.listeningEnabled).toBe(false);
    expect(runtime.sessionId).toBeNull();
    expect(runtime.stream).toBeNull();
    expect(runtime.audioContext).toBeNull();
    expect(track.stop).toHaveBeenCalledOnce();
    expect(runtime.request).toHaveBeenCalledWith(
      "/voice/sessions/voice-session",
      { method: "DELETE" }
    );
    expect(onState).toHaveBeenLastCalledWith("Voice listening is off");

    runtime.start = vi.fn(async () => {
      runtime.sessionId = "replacement-session";
      runtime.stream = { getTracks: () => [] };
      runtime.audioContext = { state: "running" };
      runtime.transition("WAITING_FOR_WAKE");
      onState("Listening for Mjolnir");
    });
    await runtime.resume();

    expect(runtime.start).toHaveBeenCalledOnce();
    expect(runtime.sessionId).toBe("replacement-session");
    expect(runtime.sessionActive).toBe(true);
    expect(runtime.paused).toBe(false);
    expect(runtime.listeningEnabled).toBe(true);
    expect(onState).toHaveBeenLastCalledWith("Listening for Mjolnir");
  });

  test("cleanup continues when a track and AudioContext fail to close", async () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    const runtime = new VoiceRuntime({
      apiBaseUrl: "/api/v1",
      onCommand: vi.fn(),
      onWake: vi.fn(),
      onState: vi.fn(),
      onInterruption: vi.fn()
    });
    const brokenTrack = { stop: vi.fn(() => { throw new Error("track failure"); }) };
    const healthyTrack = { stop: vi.fn() };
    runtime.sessionId = "voice-session";
    runtime.stream = { getTracks: () => [brokenTrack, healthyTrack] };
    runtime.audioContext = { state: "running", close: vi.fn().mockRejectedValue(new Error("context failure")) };
    runtime.request = vi.fn().mockResolvedValue({ state: "listening_for_wake_word" });

    await runtime.stop();

    expect(brokenTrack.stop).toHaveBeenCalledOnce();
    expect(healthyTrack.stop).toHaveBeenCalledOnce();
    expect(runtime.audioContext).toBeNull();
    expect(runtime.stream).toBeNull();
    expect(runtime.request).toHaveBeenCalledWith(
      "/voice/sessions/voice-session",
      { method: "DELETE" }
    );
    expect(error).toHaveBeenCalledWith(expect.objectContaining({ event: "voice_track_cleanup_failure" }));
    expect(error).toHaveBeenCalledWith(expect.objectContaining({ event: "voice_audio_context_cleanup_failure" }));
    error.mockRestore();
  });

  test("concurrent cleanup requests release resources only once", async () => {
    const runtime = new VoiceRuntime({
      apiBaseUrl: "/api/v1",
      onCommand: vi.fn(),
      onWake: vi.fn(),
      onState: vi.fn(),
      onInterruption: vi.fn()
    });
    const track = { stop: vi.fn() };
    let finishClose;
    runtime.sessionId = "voice-session";
    runtime.stream = { getTracks: () => [track] };
    const audioContext = {
      state: "running",
      close: vi.fn(() => new Promise((resolve) => { finishClose = resolve; }))
    };
    runtime.audioContext = audioContext;
    runtime.request = vi.fn().mockResolvedValue({ state: "listening_for_wake_word" });

    const first = runtime.releaseResources("quit");
    const second = runtime.releaseResources("quit");
    finishClose();
    await Promise.all([first, second]);

    expect(track.stop).toHaveBeenCalledOnce();
    expect(audioContext.close).toHaveBeenCalledOnce();
    expect(runtime.request).toHaveBeenCalledOnce();
  });

  test("recreates a backend session after an audio request reports a stale session", async () => {
    const debug = vi.spyOn(console, "debug").mockImplementation(() => {});
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    const onState = vi.fn();
    const runtime = new VoiceRuntime({
      apiBaseUrl: "/api/v1",
      onCommand: vi.fn(),
      onWake: vi.fn(),
      onState,
      onInterruption: vi.fn()
    });
    runtime.sessionId = "stale-session";
    runtime.audioContext = { sampleRate: 16000 };
    runtime.voiceState = "WAITING_FOR_WAKE";
    const staleError = Object.assign(new Error("Voice session was not found."), {
      status: 404,
      path: "/voice/sessions/stale-session/audio",
      method: "POST",
      responseBody: '{"detail":"Voice session was not found."}'
    });
    runtime.request = vi.fn()
      .mockRejectedValueOnce(staleError)
      .mockResolvedValueOnce({
        session_id: "replacement-session",
        state: "listening_for_wake_word"
      });

    runtime.process(samples());
    await runtime.chain;

    expect(runtime.request).toHaveBeenNthCalledWith(
      2,
      "/voice/sessions",
      { method: "POST" }
    );
    expect(runtime.sessionId).toBe("replacement-session");
    expect(runtime.voiceState).toBe("WAITING_FOR_WAKE");
    expect(runtime.capturePaused).toBe(false);
    expect(onState).toHaveBeenLastCalledWith("Listening for Mjolnir");
    expect(error).toHaveBeenCalledWith(expect.objectContaining({
      event: "voice_connection_closed",
      close_code: 404
    }));
    debug.mockRestore();
    error.mockRestore();
  });
});
