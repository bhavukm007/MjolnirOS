import { useAssistantState } from "../../state/AssistantStateProvider.jsx";

const particles = Array.from({ length: 24 }, (_, index) => ({ angle: index * 15, delay: -((index * 0.37) % 6), distance: 118 + (index % 4) * 12, size: 2 + (index % 3) }));
const stateLabels = { idle: "Ready", "wake-word": "Awake", listening: "Listening", thinking: "Thinking", speaking: "Speaking", "executing-tool": "Executing", success: "Complete", error: "Attention", paused: "Paused", offline: "Offline" };

export default function MjolnirCore({ connectionState = "online", className = "" }) {
  const { state, audioLevel, suspended } = useAssistantState();
  const visibleState = connectionState === "offline" ? "offline" : state;
  return (
    <div aria-label={`Mjolnir Core: ${stateLabels[visibleState]}`} className={`mjolnir-core mjolnir-core--${visibleState} ${suspended ? "is-suspended" : ""} ${className}`} role="img" style={{ "--audio-level": audioLevel.toFixed(3) }}>
      <div className="core-ambient" />
      <div className="core-pulse core-pulse--one" /><div className="core-pulse core-pulse--two" />
      <div className="core-ring core-ring--outer"><i /><i /><i /></div>
      <div className="core-ring core-ring--middle"><i /><i /></div>
      <div className="core-ring core-ring--inner"><i /><i /><i /></div>
      <div className="core-particles" aria-hidden="true">{particles.map((particle, index) => <i key={index} style={{ "--angle": `${particle.angle}deg`, "--delay": `${particle.delay}s`, "--distance": `${particle.distance}px`, "--size": `${particle.size}px` }} />)}</div>
      <svg aria-hidden="true" className="core-arcs" viewBox="0 0 360 360"><defs><filter id="core-glow"><feGaussianBlur stdDeviation="2.4" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter></defs><g filter="url(#core-glow)"><path d="M80 226 C112 242, 116 275, 153 267 S205 224, 242 244 S287 229, 296 198" /><path d="M68 154 C101 138, 115 98, 151 111 S190 157, 225 130 S271 117, 293 145" /><path d="M103 96 C118 119, 137 126, 154 105 S191 75, 212 100 S250 119, 267 94" /></g></svg>
      <div className="core-sphere"><span className="core-sphere__mesh" /><span className="core-sphere__energy" /><span className="core-sphere__highlight" /><svg aria-hidden="true" className="core-glyph" viewBox="0 0 100 100"><path d="M29 31h42L59 47v26H41V47L29 31Zm12 42h18M36 24h28" /></svg></div>
      <div className="core-state-label"><span>{stateLabels[visibleState]}</span><i /></div>
    </div>
  );
}
