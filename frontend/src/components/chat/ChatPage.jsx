import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";

import { useAssistantState } from "../../state/AssistantStateProvider.jsx";
import { VoiceRuntime } from "../../voice_runtime.js";
import { Button, GlassCard, Icon, StatusPill } from "../ui/index.js";

const STORAGE_KEY = "mjolnir.conversation";
const ConversationContext = createContext(null);

export function ConversationProvider({ apiBaseUrl, children }) {
  const { acceptVoiceState, setAudioLevel, setState: setAssistantState } = useAssistantState();
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState([]);
  const [state, setState] = useState("Voice checking");
  const [listening, setListening] = useState(false);
  const runtime = useRef(null);
  const messagesRef = useRef(messages);
  const speechRequest = useRef(0);
  const turnSequence = useRef(Date.now());

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    try { window.localStorage?.removeItem(STORAGE_KEY); } catch { /* Chat still starts empty when storage is unavailable. */ }
  }, []);

  useEffect(() => {
    let active = true;
    const voice = createVoiceRuntime();
    runtime.current = voice;
    void voice.start().then(async () => { if (!active) await voice.stop(); }).catch((error) => {
      if (active && runtime.current === voice) { setListening(false); setState(error.message); }
    });
    return () => { active = false; if (runtime.current === voice) runtime.current = null; void voice.stop(); };
  }, []);

  function createVoiceRuntime() {
    let voice;
    voice = new VoiceRuntime({
      apiBaseUrl,
      onCommand: (message, onVoicePhase) => send(message, { voice: true, onVoicePhase }),
      onWake: async () => {
        const response = await fetch(`${apiBaseUrl}/voice/speak?wait=true`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: "Yes, Boss." }) });
        if (!response.ok) throw new Error("Wake acknowledgement TTS failed.");
      },
      onState: (nextState) => { if (runtime.current !== voice) return; setListening(voice.listeningEnabled); setState(nextState); },
      onAmplitude: setAudioLevel,
      onVoiceState: acceptVoiceState,
      onInterruption: () => { if (!runtime.current?.capturePaused) void fetch(`${apiBaseUrl}/voice/speak`, { method: "DELETE" }); }
    });
    return voice;
  }

  async function send(rawMessage, { voice = false, onVoicePhase } = {}) {
    const message = rawMessage.trim();
    if (!message) return;

    const turnId = ++turnSequence.current;
    const assistantId = `${turnId}-assistant`;
    const history = messagesRef.current
      .filter((item) => item.role === "You" || item.role === "Mjolnir")
      .filter((item) => !item.pending && item.text?.trim())
      .slice(-30)
      .map((item) => ({ role: item.role === "You" ? "user" : "assistant", content: item.text }));

    setAssistantState("thinking");
    setMessages((current) => [
      ...current,
      { id: `${turnId}-user`, role: "You", text: message, voice },
      { id: assistantId, role: "Mjolnir", text: "", pending: true, streaming: true }
    ]);
    setDraft("");

    try {
      const response = await fetch(`${apiBaseUrl}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, history })
      });
      if (!response.ok) throw new Error(`Assistant request failed with status ${response.status}.`);

      const reader = response.body?.getReader();
      if (!reader) throw new Error("The assistant response stream is unavailable.");
      const decoder = new TextDecoder();
      const toolEvents = [];
      let answer = "";
      let buffer = "";

      const consumeLine = (line) => {
        if (!line.trim()) return;
        const event = JSON.parse(line);
        if (event.type === "error") throw new Error(event.message ?? "The assistant stream failed.");
        if (event.type === "token") {
          answer += event.content ?? "";
          setMessages((current) => current.map((item) => item.id === assistantId ? { ...item, text: answer, pending: false } : item));
        }
        if (["tool_start", "tool_result", "tool_error"].includes(event.type)) {
          toolEvents.push(event);
          setAssistantState(event.type === "tool_start" ? "executing-tool" : event.type === "tool_error" ? "error" : "success");
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        lines.forEach(consumeLine);
        if (done) break;
      }
      consumeLine(buffer);

      const addressedAnswer = addressBoss(answer || "No response received.");
      const shouldSpeak = Boolean(runtime.current?.listeningEnabled);
      setMessages((current) => current.flatMap((item) => item.id === assistantId
        ? [
            ...toolEvents.map((event, index) => ({ id: `${turnId}-tool-${index}`, role: "Tool", text: event.content ?? event.message ?? event.name ?? "Tool execution", toolState: event.type })),
            { id: assistantId, role: "Mjolnir", text: addressedAnswer, voice, spoken: shouldSpeak }
          ]
        : item));

      onVoicePhase?.("TOOL_COMPLETION", { response_length: addressedAnswer.length });
      if (shouldSpeak) {
        setAssistantState("speaking");
        onVoicePhase?.("TTS_START", { utterance: "command_response" });
        const requestId = ++speechRequest.current;
        runtime.current?.beginPlayback("assistant_reply_tts");
        try {
          const speech = await fetch(`${apiBaseUrl}/voice/speak?wait=true`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: addressedAnswer }) });
          if (!speech.ok) { const failure = await speech.json().catch(() => ({})); throw new Error(failure.detail ?? "Assistant reply TTS failed."); }
        } catch (error) {
          onVoicePhase?.("TTS_FAILURE", { error: error.message });
          if (requestId === speechRequest.current) setState(`Speech failed: ${error.message}`);
        } finally {
          runtime.current?.endPlayback("assistant_reply_tts_complete");
          onVoicePhase?.("TTS_END", { utterance: "command_response" });
        }
      }
      setAssistantState(runtime.current?.listeningEnabled ? "idle" : "paused");
    } catch (error) {
      setAssistantState("error");
      setMessages((current) => current.map((item) => item.id === assistantId ? { ...item, text: error.message, pending: false, streaming: false, error: true } : item));
    }
  }

  async function toggleVoice() {
    try {
      if (runtime.current?.listeningEnabled) { await runtime.current.pause(); return; }
      if (!runtime.current) runtime.current = createVoiceRuntime();
      await runtime.current.resume();
    } catch (error) {
      setListening(Boolean(runtime.current?.listeningEnabled));
      setState(error.message);
    }
  }

  const value = useMemo(() => ({ draft, listening, messages, send, setDraft, state, toggleVoice }), [draft, listening, messages, state]);
  return <ConversationContext.Provider value={value}>{children}</ConversationContext.Provider>;
}

export default function ChatPage({ compact = false }) {
  const conversation = useContext(ConversationContext);
  const messageList = useRef(null);
  if (!conversation) throw new Error("ChatPage must be rendered inside ConversationProvider.");
  const { draft, listening, messages, send, setDraft, state, toggleVoice } = conversation;

  useEffect(() => { messageList.current?.scrollTo?.({ top: messageList.current.scrollHeight, behavior: "smooth" }); }, [messages]);

  return <GlassCard className={`chat-page os-page-enter ${compact ? "chat-page--compact" : ""}`}>
    <header className="chat-header"><div className="chat-header__identity"><span className="chat-header__mark"><Icon name="command" size={18} /></span><div><h2>{compact ? "Conversation" : "Mjolnir conversation"}</h2><p>{state}</p></div></div><div className="chat-header__controls"><StatusPill label={listening ? "Listening" : "Voice paused"} status={listening ? "listening" : "paused"} /><Button aria-label={listening ? "Pause Listening" : "Resume Listening"} onClick={toggleVoice} size="sm" variant={listening ? "secondary" : "primary"}><Icon name="microphone" size={15} /><span className="chat-voice-label">{listening ? "Pause Listening" : "Resume Listening"}</span></Button></div></header>
    <div className="chat-messages" ref={messageList}>
      {messages.length === 0 ? <div className="chat-empty"><h3>How can I help, Boss?</h3><p>Type a command or speak naturally. Every response stays in this conversation.</p><div className="chat-suggestions"><button onClick={() => setDraft("Summarize my recent activity")} type="button">Summarize activity</button><button onClick={() => setDraft("Open my browser workspace")} type="button">Open browser</button><button onClick={() => setDraft("Show system health")} type="button">System health</button></div></div> : messages.map((item) => item.role === "Tool" ? <ToolCard item={item} key={item.id} /> : <MessageCard item={item} key={item.id} />)}
    </div>
    <form className="chat-composer" onSubmit={(event) => { event.preventDefault(); void send(draft); }}><div className="chat-composer__field"><Button aria-label="Attach file" size="sm" type="button" variant="ghost"><Icon name="file" size={17} /></Button><textarea aria-label="Message Mjolnir" className="os-input" onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(draft); } }} placeholder="Type a command or say Mjolnir" rows="1" value={draft} /><Button aria-label="Send" disabled={!draft.trim()} size="sm" type="submit" variant="primary"><Icon name="send" size={16} /><span className="chat-send-label">Send</span></Button></div><div className="chat-composer__meta"><span>Enter to send · Shift + Enter for a new line</span><span><i />Processed locally</span></div></form>
  </GlassCard>;
}

function MessageCard({ item }) {
  return <article className={`chat-message chat-message--${item.role === "You" ? "user" : "assistant"} ${item.error ? "is-error" : ""}`}><div className="chat-message__avatar">{item.role === "You" ? <Icon name="user" size={15} /> : <Icon name="command" size={15} />}</div><div className="chat-message__body"><div className="chat-message__meta"><strong>{item.role}</strong>{item.voice && <span><Icon name="microphone" size={11} />Voice</span>}{item.spoken && !item.voice && <span><Icon name="microphone" size={11} />Spoken</span>}{item.streaming && !item.pending && <span className="chat-streaming">Streaming</span>}</div>{item.pending ? <div className="thinking-dots"><i /><i /><i /></div> : <MarkdownMessage text={item.text} />}</div></article>;
}

function MarkdownMessage({ text }) {
  const blocks = text.split(/```/);
  return <div className="chat-markdown">{blocks.map((block, index) => index % 2 ? <pre key={index}><code>{block.replace(/^\w+\n/, "")}</code></pre> : block.split("\n").filter(Boolean).map((line, lineIndex) => <p key={`${index}-${lineIndex}`}>{line.replace(/^[-*]\s+/, "• ")}</p>))}</div>;
}

function ToolCard({ item }) {
  const failed = item.toolState === "tool_error";
  return <article className={`tool-card ${failed ? "tool-card--error" : ""}`}><span className="tool-card__icon"><Icon name={failed ? "activity" : "command"} size={16} /></span><div><span className="os-eyebrow">Tool execution</span><strong>{item.text}</strong></div><StatusPill label={failed ? "Failed" : item.toolState === "tool_start" ? "Running" : "Complete"} status={failed ? "error" : item.toolState === "tool_start" ? "listening" : "success"} /></article>;
}

function addressBoss(reply) {
  if (/\bboss\b/i.test(reply)) return reply;
  const trimmed = reply.trim();
  return trimmed ? `${trimmed.replace(/[.!?]+$/, "")}, Boss.` : trimmed;
}
