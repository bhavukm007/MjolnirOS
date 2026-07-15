import MjolnirCore from "./MjolnirCore.jsx";
import { GlassCard } from "../ui/index.js";

export default function CoreDashboard({ connectionState, conversation }) {
  return <section className="core-dashboard">
    <GlassCard className="core-dashboard__hero"><div className="core-dashboard__caption"><span className="os-eyebrow">Mjolnir Core</span><p>Local intelligence engine</p></div><MjolnirCore connectionState={connectionState} /><div className="core-dashboard__privacy"><span />Encrypted on device</div></GlassCard>
    <aside aria-label="Mjolnir conversation" className="core-dashboard__conversation">{conversation}</aside>
  </section>;
}
