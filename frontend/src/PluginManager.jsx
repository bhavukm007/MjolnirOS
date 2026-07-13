import { useEffect, useState } from "react";

export default function PluginManager({ request }) {
  const [installed, setInstalled] = useState([]);
  const [marketplace, setMarketplace] = useState([]);
  const [categories, setCategories] = useState([]);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [view, setView] = useState("installed");
  const [error, setError] = useState("");
  const [busyPluginId, setBusyPluginId] = useState(null);

  async function loadPlugins() {
    try {
      setError("");
      const query = new URLSearchParams();
      if (search.trim()) query.set("search", search.trim());
      if (category) query.set("category", category);
      const suffix = query.size ? `?${query}` : "";
      const [installedData, marketplaceData, categoryData] = await Promise.all([
        request(`/plugins${suffix}`),
        request(`/plugins/marketplace${suffix}`),
        request("/plugins/categories")
      ]);
      setInstalled(installedData);
      setMarketplace(marketplaceData);
      setCategories(categoryData);
    } catch (loadError) {
      setError(loadError.message);
    }
  }

  useEffect(() => {
    loadPlugins();
  }, []);

  async function managePlugin(pluginId, action) {
    try {
      setError("");
      setBusyPluginId(pluginId);
      const path = action === "uninstall" ? `/plugins/${pluginId}` : `/plugins/${pluginId}/${action}`;
      await request(path, { method: action === "uninstall" ? "DELETE" : "POST" });
      await loadPlugins();
    } catch (actionError) {
      setError(actionError.message);
    } finally {
      setBusyPluginId(null);
    }
  }

  const plugins = view === "installed" ? installed : marketplace;

  return (
    <section className="rounded-md border border-white/10 bg-white/[0.04] p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Plugin Manager</h2>
          <p className="mt-1 text-sm text-slate-300">Manage isolated local extensions without restarting MjolnirOS.</p>
        </div>
        <button className="rounded border border-white/15 bg-black/20 px-3 py-2 text-sm" onClick={loadPlugins} type="button">Refresh</button>
      </div>
      <div className="mt-4 flex flex-wrap gap-2" role="tablist" aria-label="Plugin views">
        <button aria-selected={view === "installed"} className={`rounded px-3 py-2 text-sm ${view === "installed" ? "bg-cyan-400 font-semibold text-slate-950" : "bg-white/10"}`} onClick={() => setView("installed")} role="tab" type="button">Installed plugins</button>
        <button aria-selected={view === "marketplace"} className={`rounded px-3 py-2 text-sm ${view === "marketplace" ? "bg-cyan-400 font-semibold text-slate-950" : "bg-white/10"}`} onClick={() => setView("marketplace")} role="tab" type="button">Marketplace</button>
      </div>
      <form className="mt-4 flex flex-wrap gap-2" onSubmit={(event) => { event.preventDefault(); loadPlugins(); }}>
        <input aria-label="Search plugins" className="min-w-48 flex-1 rounded border border-white/15 bg-black/20 px-3 py-2 text-sm" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search plugins" />
        <select aria-label="Plugin category" className="rounded border border-white/15 bg-black/20 px-3 py-2 text-sm" value={category} onChange={(event) => setCategory(event.target.value)}><option value="">All categories</option>{categories.map((item) => <option key={item} value={item}>{item}</option>)}</select>
        <button className="rounded bg-white/10 px-3 py-2 text-sm" type="submit">Search</button>
      </form>
      {error && <p className="mt-3 text-sm text-red-200">{error}</p>}
      <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {plugins.map((plugin) => {
          const record = view === "installed" ? plugin : { ...plugin, status: plugin.installed ? "disabled" : null };
          const { manifest } = record;
          const isInstalled = view === "installed" || plugin.installed;
          const isEnabled = record.status === "loaded";
          const busy = busyPluginId === manifest.id;
          return <article className="rounded border border-white/10 bg-black/20 p-4" key={manifest.id}><div className="flex items-start justify-between gap-3"><h3 className="font-medium">{manifest.name}</h3><span className="text-xs text-slate-400">v{manifest.version}</span></div><p className="mt-2 min-h-10 text-xs leading-5 text-slate-400">{manifest.description}</p><p className="mt-2 text-xs text-cyan-100">{manifest.category} · {isInstalled ? (isEnabled ? "enabled" : "disabled") : "available"}</p>{view === "installed" && record.blocked_reason && <p className="mt-2 text-xs text-amber-200">{record.blocked_reason}</p>}<div className="mt-4 flex flex-wrap gap-3 text-xs">{!isInstalled ? <Action label="Install" onClick={() => managePlugin(manifest.id, "install")} busy={busy} /> : <>{isEnabled ? <Action label="Disable" onClick={() => managePlugin(manifest.id, "disable")} busy={busy} /> : <Action label="Load / Enable" onClick={() => managePlugin(manifest.id, "load")} busy={busy} />}{plugin.update_available && view === "marketplace" && <Action label="Update" onClick={() => managePlugin(manifest.id, "update")} busy={busy} />}{view === "installed" && <Action label="Update" onClick={() => managePlugin(manifest.id, "update")} busy={busy} />}{view === "installed" && <Action label="Uninstall" tone="danger" onClick={() => managePlugin(manifest.id, "uninstall")} busy={busy} />}</>}</div></article>;
        })}
      </div>
      {plugins.length === 0 && <p className="mt-5 text-sm text-slate-400">No plugins match this search.</p>}
    </section>
  );
}

function Action({ label, tone = "default", onClick, busy }) {
  return <button className={tone === "danger" ? "text-red-200" : "text-cyan-200"} disabled={busy} onClick={onClick} type="button">{busy ? "Working…" : label}</button>;
}
