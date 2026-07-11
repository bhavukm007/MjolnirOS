import { useEffect, useMemo, useState } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

const initialHealth = {
  status: "starting",
  app_name: "MjolnirOS",
  environment: "development",
  version: "0.1.0",
  default_model: "qwen2.5:3b",
  modules: []
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

export default function App() {
  const [health, setHealth] = useState(initialHealth);
  const [settings, setSettings] = useState(null);
  const [connectionState, setConnectionState] = useState("connecting");

  useEffect(() => {
    let active = true;

    async function loadDashboard() {
      try {
        const [healthData, settingsData] = await Promise.all([
          fetchJson("/health"),
          fetchJson("/settings")
        ]);
        if (active) {
          setHealth(healthData);
          setSettings(settingsData);
          setConnectionState("online");
        }
      } catch (error) {
        if (active) {
          setConnectionState("offline");
        }
      }
    }

    loadDashboard();
    const intervalId = window.setInterval(loadDashboard, 10000);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, []);

  const moduleCount = useMemo(() => health.modules.length, [health.modules]);

  return (
    <main className="min-h-screen bg-[#090b10] text-slate-100">
      <section className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-8 px-6 py-8">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-6">
          <div>
            <h1 className="text-3xl font-semibold tracking-normal">{health.app_name}</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
              Local-first desktop operating assistant foundation.
            </p>
          </div>
          <div className="flex items-center gap-3 rounded-md border border-white/10 bg-white/5 px-4 py-3">
            <span className={`h-2.5 w-2.5 rounded-full ${connectionState === "online" ? "bg-emerald-400" : "bg-amber-400"}`} />
            <span className="text-sm font-medium capitalize">{connectionState}</span>
          </div>
        </header>

        <section className="grid gap-4 md:grid-cols-4">
          <StatusTile label="Backend" value={health.status} />
          <StatusTile label="Environment" value={health.environment} />
          <StatusTile label="Default Model" value={health.default_model} />
          <StatusTile label="Foundation Modules" value={String(moduleCount)} />
        </section>

        <section className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-md border border-white/10 bg-white/[0.04] p-5 shadow-2xl shadow-black/20">
            <h2 className="text-lg font-semibold">Foundation Modules</h2>
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              {health.modules.map((moduleName) => (
                <div key={moduleName} className="rounded-md border border-white/10 bg-black/20 px-4 py-3">
                  <div className="text-sm font-medium capitalize">{moduleName.replaceAll("_", " ")}</div>
                  <div className="mt-1 text-xs text-emerald-300">Ready</div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-md border border-white/10 bg-white/[0.04] p-5 shadow-2xl shadow-black/20">
            <h2 className="text-lg font-semibold">Runtime</h2>
            <dl className="mt-5 space-y-4 text-sm">
              <RuntimeRow label="API Prefix" value={settings?.api_prefix ?? "/api/v1"} />
              <RuntimeRow label="Version" value={health.version} />
              <RuntimeRow label="Config" value={settings ? "Loaded" : "Pending"} />
              <RuntimeRow label="Logging" value="Structured JSON" />
            </dl>
          </div>
        </section>
      </section>
    </main>
  );
}

function StatusTile({ label, value }) {
  return (
    <div className="rounded-md border border-white/10 bg-white/[0.04] p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-3 text-xl font-semibold capitalize text-white">{value}</div>
    </div>
  );
}

function RuntimeRow({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-white/10 pb-3">
      <dt className="text-slate-400">{label}</dt>
      <dd className="text-right font-medium text-slate-100">{value}</dd>
    </div>
  );
}
