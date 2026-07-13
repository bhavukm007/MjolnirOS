import { useEffect, useState } from "react";

const PROVIDERS = ["discord", "slack", "whatsapp", "telegram", "microsoft-teams"];

export default function CommunicationPlugins({ request }) {
  const [connections, setConnections] = useState([]); const [error, setError] = useState("");
  async function load() { try { setConnections(await request("/communication/connections")); setError(""); } catch (e) { setError(e.message); } }
  useEffect(() => { load(); }, []);
  return <section className="rounded-md border border-white/10 bg-white/[0.04] p-5"><div className="flex items-center justify-between gap-3"><div><h2 className="text-lg font-semibold">Communication Plugins</h2><p className="mt-1 text-sm text-slate-300">Credentials stay protected with Windows DPAPI. Every external message needs a separate confirmation.</p></div><button className="rounded border border-white/15 bg-black/20 px-3 py-2 text-sm" onClick={load} type="button">Refresh status</button></div>{error && <p className="mt-3 text-sm text-red-200">{error}</p>}<div className="mt-5 grid gap-3 md:grid-cols-2">{PROVIDERS.map((provider) => { const item = connections.find((connection) => connection.provider === provider); return <article className="rounded border border-white/10 bg-black/20 p-4" key={provider}><div className="flex justify-between"><h3 className="font-medium capitalize">{provider.replaceAll("-", " ")}</h3><span className={`h-2.5 w-2.5 rounded-full ${item?.connected ? "bg-emerald-400" : "bg-slate-500"}`} /></div><p className="mt-2 text-xs text-cyan-100">{item?.connected ? `Connected: ${item.account_label}` : "Not connected"}</p><p className="mt-3 text-xs text-slate-400">Read and search are available where supported. Drafts never send automatically.</p></article>; })}</div><p className="mt-5 text-xs text-slate-400">Voice calling is intentionally not enabled; the plugin boundary is reserved for a future approved implementation.</p></section>;
}
