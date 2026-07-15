import { useEffect, useState } from "react";

import { GlassCard } from "./components/ui/index.js";

const toggles = [["Start with Windows", "start_with_windows"], ["Launch minimized", "launch_minimized"], ["Minimize to tray", "minimize_to_tray"], ["Enable memory", "memory_enabled"], ["Enable notifications", "notifications_enabled"], ["Quiet hours", "quiet_hours_enabled"]];

function applyTheme(theme) {
  const resolved = theme === "system" ? (window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark") : theme;
  document.documentElement.dataset.theme = resolved;
  window.localStorage?.setItem("mjolnir.theme", theme);
}

export default function SettingsPanel({ request }) {
  const [settings, setSettings] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    request("/settings/user").then((value) => { if (active) { setSettings(value); applyTheme(value.theme); setError(""); } }).catch((reason) => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, [request]);

  async function update(key, value) {
    try {
      const saved = await request("/settings/user", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ [key]: value }) });
      setSettings(saved);
      if (key === "theme") applyTheme(value);
      window.mjolniros?.updateDesktopSettings?.(saved);
      setError("");
    } catch (reason) { setError(reason.message); }
  }

  if (!settings) return <div className="os-loading" role="status"><span />{error || "Loading settings…"}</div>;
  return <GlassCard className="settings-page">
    <div className="settings-heading"><span className="os-eyebrow">Preferences</span><h2>Settings & Security</h2><p>Local preferences, notifications, startup behavior, and permission-aware integrations.</p></div>
    {error && <p className="settings-error" role="alert">{error}</p>}
    <div className="settings-section"><h3>Desktop & privacy</h3><div className="settings-toggle-grid">{toggles.map(([label, key]) => <label className="settings-toggle" key={key}><span>{label}<small>{key === "start_with_windows" ? "Launch automatically after sign in" : key.replaceAll("_", " ")}</small></span><input checked={settings[key]} onChange={(event) => void update(key, event.target.checked)} type="checkbox" /><i aria-hidden="true" /></label>)}</div></div>
    <div className="settings-section settings-fields"><label>Theme<select className="os-input" value={settings.theme} onChange={(event) => void update("theme", event.target.value)}><option value="dark">Dark</option><option value="light">Light</option><option value="system">System</option></select></label><label>Ollama model<input className="os-input" value={settings.model} onChange={(event) => void update("model", event.target.value)} /></label></div>
  </GlassCard>;
}
