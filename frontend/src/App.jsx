import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Cpu,
  HardDrive,
  MonitorCog,
  Settings,
  ShieldCheck,
  Sparkles
} from "lucide-react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

const initialHealth = {
  status: "starting",
  app_name: "MjolnirOS",
  environment: "development",
  version: "0.1.0",
  default_model: "qwen2.5:3b",
  modules: []
};

const initialSystemStatus = {
  cpuCount: 0,
  cpuModel: "Loading system status",
  memoryUsedBytes: 0,
  memoryTotalBytes: 0,
  runningAgents: 0,
  uptimeSeconds: 0
};

async function fetchJson(path) {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }
  const body = await response.json();
  if (!body.success) {
    throw new Error(body.message);
  }
  return body.data;
}

function getDesktopApi() {
  return window.mjolniros?.desktop;
}

function formatBytes(bytes) {
  if (!bytes) {
    return "Loading";
  }
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

function formatUptime(seconds) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${minutes}m`;
}

export default function App() {
  const view = new URLSearchParams(window.location.search).get("view");
  return view === "settings" ? <SettingsScreen /> : <Dashboard />;
}

export function Dashboard() {
  const [health, setHealth] = useState(initialHealth);
  const [settings, setSettings] = useState(null);
  const [systemStatus, setSystemStatus] = useState(initialSystemStatus);
  const [connectionState, setConnectionState] = useState("connecting");

  useEffect(() => {
    let active = true;

    async function loadDashboard() {
      try {
        const desktopApi = getDesktopApi();
        const [healthData, settingsData, systemData] = await Promise.all([
          fetchJson("/health"),
          fetchJson("/settings"),
          desktopApi ? desktopApi.getSystemStatus() : Promise.resolve(initialSystemStatus)
        ]);
        if (active) {
          setHealth(healthData);
          setSettings(settingsData);
          setSystemStatus(systemData);
          setConnectionState("online");
        }
      } catch (error) {
        if (active) {
          setConnectionState("offline");
        }
      }
    }

    loadDashboard();
    const intervalId = window.setInterval(loadDashboard, 10_000);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, []);

  const moduleCount = useMemo(() => health.modules.length, [health.modules]);

  return (
    <main className="min-h-screen bg-[#090f1a] text-slate-100">
      <section className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-5 py-5 sm:px-8 sm:py-7">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-700/60 pb-5">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-md border border-teal-300/30 bg-teal-300/10 text-teal-200">
              <Sparkles aria-hidden="true" size={20} />
            </div>
            <div>
              <h1 className="text-xl font-semibold">{health.app_name}</h1>
              <p className="mt-1 text-sm text-slate-400">Desktop runtime</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 rounded-md border border-slate-700 bg-slate-900/70 px-3 py-2">
              <span className={`h-2 w-2 rounded-full ${connectionState === "online" ? "bg-emerald-400" : "bg-amber-400"}`} />
              <span className="text-xs font-medium uppercase tracking-wide text-slate-300">{connectionState}</span>
            </div>
            <button className="command-button" onClick={() => getDesktopApi()?.openSettings()} type="button">
              <Settings aria-hidden="true" size={16} />
              <span>Settings</span>
            </button>
          </div>
        </header>

        <section aria-label="System overview" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard icon={Cpu} label="CPU" value={systemStatus.cpuCount ? `${systemStatus.cpuCount} cores` : "Loading"} detail={systemStatus.cpuModel} />
          <MetricCard icon={HardDrive} label="RAM" value={`${formatBytes(systemStatus.memoryUsedBytes)} / ${formatBytes(systemStatus.memoryTotalBytes)}`} detail="Memory in use / total" />
          <MetricCard icon={Sparkles} label="Current Model" value={health.default_model} detail="Local Ollama default" />
          <MetricCard icon={Activity} label="Running Agents" value={String(systemStatus.runningAgents)} detail="No active agent workflows" />
        </section>

        <section className="grid gap-5 lg:grid-cols-[1.35fr_0.65fr]">
          <div className="glass-panel p-5">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="section-label">Runtime</p>
                <h2 className="mt-1 text-lg font-semibold">Foundation services</h2>
              </div>
              <span className="rounded-md border border-teal-300/25 bg-teal-300/10 px-2.5 py-1 text-xs font-medium text-teal-100">{moduleCount} ready</span>
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              {health.modules.map((moduleName) => (
                <div key={moduleName} className="module-row">
                  <div className="flex h-8 w-8 items-center justify-center rounded-md bg-slate-800 text-teal-200">
                    <ShieldCheck aria-hidden="true" size={16} />
                  </div>
                  <div>
                    <p className="text-sm font-medium capitalize">{moduleName.replaceAll("_", " ")}</p>
                    <p className="mt-0.5 text-xs text-emerald-300">Available</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="glass-panel p-5">
            <div className="flex items-center gap-2">
              <MonitorCog aria-hidden="true" className="text-teal-200" size={18} />
              <h2 className="text-lg font-semibold">Runtime detail</h2>
            </div>
            <dl className="mt-5 space-y-3">
              <RuntimeRow label="Backend" value={health.status} />
              <RuntimeRow label="Environment" value={health.environment} />
              <RuntimeRow label="API prefix" value={settings?.api_prefix ?? "/api/v1"} />
              <RuntimeRow label="System uptime" value={formatUptime(systemStatus.uptimeSeconds)} />
              <RuntimeRow label="Logging" value="Structured JSON" />
            </dl>
          </div>
        </section>
      </section>
    </main>
  );
}

export function SettingsScreen() {
  const [settings, setSettings] = useState({ launchOnStartup: false });
  const [status, setStatus] = useState("Loading desktop preferences");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    const desktopApi = getDesktopApi();
    if (!desktopApi) {
      setStatus("Desktop settings require the Electron runtime.");
      return;
    }

    desktopApi
      .getSettings()
      .then((loadedSettings) => {
        setSettings(loadedSettings);
        setStatus("Preferences are saved locally on this device.");
      })
      .catch(() => setStatus("Unable to load desktop preferences."));
  }, []);

  async function updateLaunchOnStartup(event) {
    const desktopApi = getDesktopApi();
    if (!desktopApi) {
      return;
    }

    setIsSaving(true);
    try {
      const updatedSettings = await desktopApi.setLaunchOnStartup(event.target.checked);
      setSettings(updatedSettings);
      setStatus(updatedSettings.launchOnStartup ? "Windows startup is enabled." : "Windows startup is disabled.");
    } catch (error) {
      setStatus("Unable to update the Windows startup preference.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#090f1a] px-5 py-5 text-slate-100 sm:px-7 sm:py-7">
      <section className="mx-auto flex min-h-[calc(100vh-2.5rem)] max-w-2xl flex-col rounded-md border border-slate-700/70 bg-slate-900/60 p-5 shadow-2xl shadow-black/30 sm:p-7">
        <header className="flex items-start justify-between gap-4 border-b border-slate-700/60 pb-5">
          <div>
            <p className="section-label">MjolnirOS</p>
            <h1 className="mt-1 text-xl font-semibold">Desktop settings</h1>
            <p className="mt-2 text-sm leading-6 text-slate-400">Control local desktop behavior and Windows startup registration.</p>
          </div>
          <div className="flex h-10 w-10 items-center justify-center rounded-md border border-teal-300/30 bg-teal-300/10 text-teal-200">
            <Settings aria-hidden="true" size={20} />
          </div>
        </header>

        <section className="mt-6" aria-labelledby="startup-heading">
          <h2 id="startup-heading" className="text-base font-semibold">Windows startup</h2>
          <div className="mt-3 flex items-center justify-between gap-5 rounded-md border border-slate-700 bg-slate-950/40 p-4">
            <div>
              <label htmlFor="launch-on-startup" className="text-sm font-medium text-slate-100">Launch MjolnirOS when Windows starts</label>
              <p className="mt-1 max-w-sm text-xs leading-5 text-slate-400">The application is registered only after you enable this option. It is off by default.</p>
            </div>
            <div className="relative inline-flex h-6 w-11 shrink-0">
              <input
                id="launch-on-startup"
                checked={settings.launchOnStartup}
                className="peer sr-only"
                disabled={isSaving}
                onChange={updateLaunchOnStartup}
                type="checkbox"
              />
              <span className="h-6 w-11 rounded-full bg-slate-700 transition peer-checked:bg-teal-500 peer-disabled:cursor-wait peer-disabled:opacity-60" />
              <span className="absolute left-1 h-4 w-4 rounded-full bg-white transition peer-checked:translate-x-5" />
            </div>
          </div>
        </section>

        <p aria-live="polite" className="mt-5 text-sm text-slate-400">{status}</p>
        <div className="mt-auto flex justify-end border-t border-slate-700/60 pt-5">
          <button className="command-button" onClick={() => getDesktopApi()?.openMainWindow()} type="button">
            <MonitorCog aria-hidden="true" size={16} />
            <span>Open dashboard</span>
          </button>
        </div>
      </section>
    </main>
  );
}

function MetricCard({ icon: Icon, label, value, detail }) {
  return (
    <article className="glass-panel min-w-0 p-4">
      <div className="flex items-center justify-between gap-3">
        <span className="section-label">{label}</span>
        <Icon aria-hidden="true" className="text-teal-200" size={17} />
      </div>
      <p className="mt-4 break-words text-xl font-semibold text-white">{value}</p>
      <p className="mt-1 truncate text-xs text-slate-400" title={detail}>{detail}</p>
    </article>
  );
}

function RuntimeRow({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-slate-700/60 pb-3 text-sm last:border-0 last:pb-0">
      <dt className="text-slate-400">{label}</dt>
      <dd className="max-w-[58%] truncate text-right font-medium capitalize text-slate-100" title={value}>{value}</dd>
    </div>
  );
}
