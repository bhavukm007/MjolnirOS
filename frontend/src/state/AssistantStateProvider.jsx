import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

const AssistantStateContext = createContext({ state: "idle", setState: () => {}, audioLevel: 0, setAudioLevel: () => {}, acceptVoiceState: () => {}, suspended: false });
const voiceStateMap = { IDLE: "idle", WAITING_FOR_WAKE: "idle", WAKE_DETECTED: "wake-word", LISTENING_FOR_COMMAND: "listening", PROCESSING: "thinking", TOOL_START: "executing-tool", TOOL_COMPLETION: "success", TTS_START: "speaking", SPEAKING: "speaking", TTS_FAILURE: "error", PAUSED: "paused" };

export function AssistantStateProvider({ children }) {
  const [state, setState] = useState("idle");
  const [audioLevel, setAudioLevelState] = useState(0);
  const [suspended, setSuspended] = useState(() => document.hidden);
  const lastAmplitudeUpdate = useRef(0);
  const setAudioLevel = useCallback((level) => {
    const now = performance.now();
    if (now - lastAmplitudeUpdate.current < 48) return;
    lastAmplitudeUpdate.current = now;
    setAudioLevelState(Math.max(0, Math.min(1, level * 5)));
  }, []);
  const acceptVoiceState = useCallback((voiceState) => { const next = voiceStateMap[voiceState]; if (next) setState(next); }, []);
  useEffect(() => { const onVisibility = () => setSuspended(document.hidden); document.addEventListener("visibilitychange", onVisibility); return () => document.removeEventListener("visibilitychange", onVisibility); }, []);
  const value = useMemo(() => ({ state, setState, audioLevel, setAudioLevel, acceptVoiceState, suspended }), [state, audioLevel, setAudioLevel, acceptVoiceState, suspended]);
  return <AssistantStateContext.Provider value={value}>{children}</AssistantStateContext.Provider>;
}

export function useAssistantState() {
  return useContext(AssistantStateContext);
}
