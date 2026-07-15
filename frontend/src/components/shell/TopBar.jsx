import { Button, Icon, StatusPill } from "../ui/index.js";

const titles = {
  dashboard: ["Command center", "Overview of your local intelligence"], chat: ["Chat", "Talk, type, and execute"],
  memory: ["Memory", "Your private knowledge context"], browser: ["Browser", "Autonomous web workspace"],
  vision: ["Vision", "Documents and screen intelligence"], automation: ["Automation", "Workflows and planned actions"],
  plugins: ["Plugins", "Extend Mjolnir safely"], settings: ["Settings", "Personalize your operating assistant"],
  productivity: ["Productivity", "Connected local workflows"], communication: ["Communication", "Messages and collaboration"]
};

export default function TopBar({ activeView, connectionState, model, onNavigate }) {
  const [title, subtitle] = titles[activeView] ?? titles.dashboard;
  return (
    <header className="os-topbar">
      <div className="os-topbar__title"><h1>{title}</h1><p>{subtitle}</p></div>
      <div className="os-topbar__actions">
        <span className="sr-only">{connectionState}</span>
        <div className="os-model-chip"><span className="os-eyebrow">Active model</span><strong>{model || "Local model"}</strong></div>
        <StatusPill label={connectionState === "online" ? "All systems online" : "Backend offline"} status={connectionState} />
        <Button aria-label="Open search" size="sm" variant="ghost"><Icon name="search" size={18} /></Button>
        <Button aria-label="Open settings" onClick={() => onNavigate("settings")} size="sm" variant="ghost"><Icon name="settings" size={18} /></Button>
        <button aria-label="User profile" className="os-avatar" type="button"><Icon name="user" size={17} /></button>
      </div>
    </header>
  );
}
