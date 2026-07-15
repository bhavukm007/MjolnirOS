import { useEffect, useRef, useState } from "react";

import { useAssistantState } from "../../state/AssistantStateProvider.jsx";
import { VoiceRuntime } from "../../voice_runtime.js";
import { Button, GlassCard, Icon, StatusPill } from "../ui/index.js";

export default function ChatPage({ apiBaseUrl, compact = false }) {
  const { acceptVoiceState, setAudioLevel, setState: setAssistantState } = useAssistantState();
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState([]);
  const [state, setState] = useState("Voice checking");
  const [listening, setListening] = useState(false);
  const runtime = useRef(null);
  const speechRequest = useRef(0);
  const messageList = useRef(null);

  useEffect(() => {
    let active = true;
    const voice = createVoiceRuntime();
    runtime.current = voice;
    void voice.start().then(async () => { if (!active) await voice.stop(); }).catch((error) => { if (active && runtime.current === voice) { setListening(false); setState(error.message); } });
    return () => { active = false; if (runtime.current === voice) runtime.current = null; void voice.stop(); };
  }, []);

  useEffect(() => { messageList.current?.scrollTo?.({ top: messageList.current.scrollHeight, behavior: "smooth" }); }, [messages]);

  function createVoiceRuntime() {
    let voice;
    voice = new VoiceRuntime({
      apiBaseUrl,
      onCommand: (message, onVoicePhase) => send(message, { voice: true, onVoicePhase }),
      onWake: async () => { const response = await fetch(`${apiBaseUrl}/voice/speak?wait=true`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: "Yes, Boss." }) }); if (!response.ok) throw new Error("Wake acknowledgement TTS failed."); },
      onState: (nextState) => { if (runtime.current !== voice) return; setListening(voice.listeningEnabled); setState(nextState); },
      onAmplitude: setAudioLevel,
      onVoiceState: acceptVoiceState,
      onInterruption: () => { if (!runtime.current?.capturePaused) void fetch(`${apiBaseUrl}/voice/speak`, { method: "DELETE" }); }
    });
    return voice;
  }

  async function send(message, { voice = false, onVoicePhase } = {}) {
    if (!message.trim()) return;
    setAssistantState("thinking");
    setMessages((current) => [...current, { role: "You", text: message, voice }, { role: "Mjolnir", text: "…", pending: true }]);
    setDraft("");
    try {
      const response = await fetch(`${apiBaseUrl}/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message, history: [] }) });
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let answer = "";
      const toolEvents = [];
      while (reader) {
        const { done, value } = await reader.read();
        if (done) break;
        decoder.decode(value).split("\n").filter(Boolean).forEach((line) => {
          const event = JSON.parse(line);
          if (event.type === "token") answer += event.content;
          if (["tool_start", "tool_result", "tool_error"].includes(event.type)) toolEvents.push(event);
        });
      }
      const addressedAnswer = addressBoss(answer || "No response received.");
      setAssistantState("speaking");
      setMessages((current) => [...current.slice(0, -1), ...toolEvents.map((event) => ({ role: "Tool", text: event.content ?? event.message ?? event.name ?? "Tool execution", toolState: event.type })), { role: "Mjolnir", text: addressedAnswer, voice }]);
      onVoicePhase?.("TOOL_COMPLETION", { response_length: addressedAnswer.length });
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
        setAssistantState(runtime.current?.listeningEnabled ? "idle" : "paused");
      }
    } catch (error) {
      setAssistantState("error");
      setMessages((current) => [...current.slice(0, -1), { role: "Mjolnir", text: error.message, error: true }]);
    }
  }

  async function toggleVoice() {
    try { if (runtime.current?.listeningEnabled) { await runtime.current.pause(); return; } if (!runtime.current) runtime.current = createVoiceRuntime(); await runtime.current.resume(); }
    catch (error) { setListening(Boolean(runtime.current?.listeningEnabled)); setState(error.message); }
  }

  return <GlassCard className={`chat-page os-page-enter ${compact ? "chat-page--compact" : ""}`}>
    <header className="chat-header"><div className="chat-header__identity"><span className="chat-header__mark"><Icon name="command" size={18} /></span><div><h2>{compact ? "Command console" : "Mjolnir conversation"}</h2><p>{state}</p></div></div><div className="chat-header__controls"><StatusPill label={listening ? "Listening" : "Voice paused"} status={listening ? "listening" : "paused"} /><Button onClick={toggleVoice} size="sm" variant={listening ? "secondary" : "primary"}><Icon name="microphone" size={15} />{listening ? "Pause Listening" : "Resume Listening"}</Button></div></header>
    <div className="chat-messages" ref={messageList}>
      {messages.length === 0 ? <div className="chat-empty"><span className="chat-empty__orb" /><h3>How can I help, Boss?</h3><p>Ask a question, run a local tool, or say “Mjolnir” to begin.</p><div className="chat-suggestions"><button onClick={() => setDraft("Summarize my recent activity")} type="button">Summarize activity</button><button onClick={() => setDraft("Open my browser workspace")} type="button">Open browser</button><button onClick={() => setDraft("Show system health")} type="button">System health</button></div></div> : messages.map((item, index) => item.role === "Tool" ? <ToolCard item={item} key={index} /> : <MessageCard item={item} key={index} />)}
    </div>
    <form className="chat-composer" onSubmit={(event) => { event.preventDefault(); void send(draft); }}><div className="chat-composer__field"><Button aria-label="Attach file" size="sm" type="button" variant="ghost"><Icon name="file" size={17} /></Button><textarea aria-label="Message Mjolnir" className="os-input" onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(draft); } }} placeholder="Type a command or say Mjolnir" rows="1" value={draft} /><Button aria-label="Send" disabled={!draft.trim()} size="sm" type="submit" variant="primary"><Icon name="send" size={16} /><span className="chat-send-label">Send</span></Button></div><div className="chat-composer__meta"><span>Enter to send · Shift + Enter for a new line</span><span><i />Processed locally</span></div></form>
  </GlassCard>;
}

function MessageCard({ item }) {
  return <article className={`chat-message chat-message--${item.role === "You" ? "user" : "assistant"} ${item.error ? "is-error" : ""}`}><div className="chat-message__avatar">{item.role === "You" ? <Icon name="user" size={15} /> : <Icon name="command" size={15} />}</div><div className="chat-message__body"><div className="chat-message__meta"><strong>{item.role}</strong>{item.voice && <span><Icon name="microphone" size={11} />Voice</span>}</div>{item.pending ? <div className="thinking-dots"><i /><i /><i /></div> : <MarkdownMessage text={item.text} />}</div></article>;
}

function MarkdownMessage({ text }) {
  const blocks = text.split(/```/);
  return <div className="chat-markdown">{blocks.map((block, index) => index % 2 ? <pre key={index}><code>{block.replace(/^\w+\n/, "")}</code></pre> : block.split("\n").filter(Boolean).map((line, lineIndex) => <p key={`${index}-${lineIndex}`}>{line.replace(/^[-*]\s+/, "• ")}</p>))}</div>;
}

function ToolCard({ item }) {
  const failed = item.toolState === "tool_error";
  return <article className={`tool-card ${failed ? "tool-card--error" : ""}`}><span className="tool-card__icon"><Icon name={failed ? "activity" : "command"} size={16} /></span><div><span className="os-eyebrow">Tool execution</span><strong>{item.text}</strong></div><StatusPill label={failed ? "Failed" : "Complete"} status={failed ? "error" : "success"} /></article>;
}

function addressBoss(reply) {
  if (/\bboss\b/i.test(reply)) return reply;
  const trimmed = reply.trim();
  return trimmed ? `${trimmed.replace(/[.!?]+$/, "")}, Boss.` : trimmed;
}
