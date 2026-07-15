import MjolnirCore from "./MjolnirCore.jsx";
import { GlassCard, Icon } from "../ui/index.js";

const quickActions = [["New conversation", "Start a focused session", "chat", "chat"], ["Open browser agent", "Research on the web", "browser", "browser"], ["Run an automation", "Execute a saved workflow", "automation", "automation"], ["Analyze a file", "Use vision and documents", "vision", "vision"]];

export default function CoreDashboard({ connectionState, onNavigate }) {
  return <section className="core-dashboard">
    <GlassCard className="core-dashboard__hero"><div className="core-dashboard__caption"><span className="os-eyebrow">Mjolnir Core</span><p>Local intelligence engine</p></div><MjolnirCore connectionState={connectionState} /><div className="core-dashboard__privacy"><span />Encrypted on device</div></GlassCard>
    <div className="quick-actions"><div className="section-heading"><div><span className="os-eyebrow">Get started</span><h3>Quick actions</h3></div><span>Ctrl + K</span></div><div className="quick-actions__grid">{quickActions.map(([title, description, icon, view]) => <GlassCard as="button" className="quick-action" interactive key={title} onClick={() => onNavigate(view)} type="button"><span className="quick-action__icon"><Icon name={icon} size={19} /></span><span><strong>{title}</strong><small>{description}</small></span><Icon className="quick-action__arrow" name="chevron" size={15} /></GlassCard>)}</div>
      <GlassCard className="recent-activity-card"><div className="section-heading"><div><span className="os-eyebrow">Activity</span><h3>Recent</h3></div><button onClick={() => onNavigate("chat")} type="button">View all</button></div><div className="activity-row"><span className="activity-row__icon"><Icon name="activity" size={16} /></span><div><strong>System ready</strong><small>All local services initialized</small></div><time>Now</time></div><div className="activity-row"><span className="activity-row__icon"><Icon name="memory" size={16} /></span><div><strong>Memory available</strong><small>Private context is ready</small></div><time>Local</time></div></GlassCard>
    </div>
  </section>;
}
