import { useEffect, useState } from "react";

import Sidebar from "./Sidebar.jsx";
import StatusBar from "./StatusBar.jsx";
import TopBar from "./TopBar.jsx";

export default function AppShell({ activeView, connectionState, health, moduleCount, onNavigate, children }) {
  const [collapsed, setCollapsed] = useState(() => window.localStorage?.getItem("mjolnir.sidebar.collapsed") === "true");
  useEffect(() => { window.localStorage?.setItem("mjolnir.sidebar.collapsed", String(collapsed)); }, [collapsed]);

  return (
    <main className={`os-shell ${collapsed ? "os-shell--collapsed" : ""}`}>
      <a className="skip-link" href="#main-workspace">Skip to workspace</a>
      <Sidebar activeView={activeView} collapsed={collapsed} onNavigate={onNavigate} onToggle={() => setCollapsed((value) => !value)} />
      <div className="os-shell__stage">
        <TopBar activeView={activeView} connectionState={connectionState} model={health.default_model} onNavigate={onNavigate} />
        <div className="os-workspace" id="main-workspace">{children}</div>
        <StatusBar connectionState={connectionState} model={health.default_model} moduleCount={moduleCount} />
      </div>
    </main>
  );
}
