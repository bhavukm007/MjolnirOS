import { Icon } from "../ui/index.js";

const primaryItems = [
  ["dashboard", "Dashboard", "dashboard"],
  ["chat", "Chat", "chat"],
  ["memory", "Memory", "memory"],
  ["browser", "Browser", "browser"],
  ["vision", "Vision", "vision"],
  ["automation", "Automation", "automation"],
  ["plugins", "Plugins", "plugins"],
  ["settings", "Settings", "settings"]
];

const integrationItems = [
  ["productivity", "Productivity", "command"],
  ["communication", "Communication", "activity"]
];

export default function Sidebar({ activeView, collapsed, onNavigate, onToggle }) {
  return (
    <aside className={`os-sidebar ${collapsed ? "os-sidebar--collapsed" : ""}`}>
      <div className="os-sidebar__brand">
        <div className="os-mark" aria-hidden="true"><span>M</span></div>
        {!collapsed && <div className="os-brand-copy"><strong>MjolnirOS</strong><span>Local Intelligence</span></div>}
        <button aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} className="os-sidebar__toggle" onClick={onToggle} type="button"><Icon name="chevron" size={16} /></button>
      </div>

      <nav aria-label="Application navigation" className="os-sidebar__nav">
        {!collapsed && <p className="os-sidebar__section">Workspace</p>}
        {primaryItems.map(([id, label, icon]) => (
          <button aria-current={activeView === id ? "page" : undefined} aria-label={id === "plugins" ? "Plugin Manager" : undefined} className={`os-nav-item ${activeView === id ? "is-active" : ""}`} key={id} onClick={() => onNavigate(id)} title={collapsed ? label : undefined} type="button">
            <Icon name={icon} size={18} />
            {!collapsed && <span>{label}</span>}
          </button>
        ))}
        {!collapsed && <p className="os-sidebar__section os-sidebar__section--spaced">Integrations</p>}
        {integrationItems.map(([id, label, icon]) => (
          <button aria-current={activeView === id ? "page" : undefined} className={`os-nav-item ${activeView === id ? "is-active" : ""}`} key={id} onClick={() => onNavigate(id)} title={collapsed ? label : undefined} type="button">
            <Icon name={icon} size={18} />
            {!collapsed && <span>{label}</span>}
          </button>
        ))}
      </nav>

      <div className="os-sidebar__footer">
        <span className="os-sidebar__local-dot" />
        {!collapsed && <div><strong>Local mode</strong><span>Your data stays here</span></div>}
      </div>
    </aside>
  );
}
