import { useEffect, useMemo, useRef, useState } from "react";

import PluginManager from "./PluginManager.jsx";
import ProductivityPlugins from "./ProductivityPlugins.jsx";
import CommunicationPlugins from "./CommunicationPlugins.jsx";
import SettingsPanel from "./SettingsPanel.jsx";
import { VoiceRuntime } from "./voice_runtime.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

const initialHealth = {
  status: "starting",
  app_name: "MjolnirOS",
  environment: "development",
  version: "1.0.0",
  default_model: "qwen2.5:3b",
  modules: []
};

async function fetchJson(path, options) {
  const response = await fetch(`${API_BASE_URL}${path}`, options);
  if (response.status === 204) return null;
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
  const [document, setDocument] = useState(null);
  const [documentResult, setDocumentResult] = useState(null);
  const [visionResult, setVisionResult] = useState(null);
  const [question, setQuestion] = useState("");
  const [agentState, setAgentState] = useState("idle");
  const [agentError, setAgentError] = useState("");
  const [workflows, setWorkflows] = useState([]);
  const [selectedWorkflow, setSelectedWorkflow] = useState(null);
  const [automationStatus, setAutomationStatus] = useState("idle");
  const [automationError, setAutomationError] = useState("");
  const [workflowDraft, setWorkflowDraft] = useState(JSON.stringify({ name: "My workflow", description: "A safe local workflow.", steps: [{ id: "announce", title: "Announce start", action: "notify", priority: 3, message: "Workflow started." }] }, null, 2));
  const [editingWorkflowId, setEditingWorkflowId] = useState(null);
  const [learning, setLearning] = useState(null);
  const [learningKind, setLearningKind] = useState("application");
  const [learningValue, setLearningValue] = useState("");
  const [learningError, setLearningError] = useState("");
  const [activeView, setActiveView] = useState("dashboard");

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

  useEffect(() => {
    if (automationStatus !== "running" || !selectedWorkflow?.execution) return undefined;
    let active = true;
    const executionId = selectedWorkflow.execution.id;
    const intervalId = window.setInterval(async () => {
      try {
        const execution = await fetchJson(`/automation/executions/${executionId}`);
        if (!active) return;
        setSelectedWorkflow((current) => ({ ...current, execution }));
        if (execution.status !== "running") setAutomationStatus(execution.status);
      } catch (error) {
        if (active) setAutomationError(error.message);
      }
    }, 500);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, [automationStatus, selectedWorkflow?.execution?.id]);

  async function loadWorkflows() {
    try {
      const data = await fetchJson("/automation/workflows");
      setWorkflows(data);
    } catch (error) {
      setAutomationError(error.message);
    }
  }

  async function runWorkflow(workflow) {
    setAutomationStatus("starting");
    setAutomationError("");
    try {
      const execution = await fetchJson(`/automation/workflows/${workflow.id}/executions`, { method: "POST" });
      setSelectedWorkflow({ ...workflow, execution });
      setAutomationStatus("running");
    } catch (error) {
      setAutomationError(error.message);
      setAutomationStatus("error");
    }
  }

  async function cancelWorkflow() {
    if (!selectedWorkflow?.execution) return;
    try {
      const execution = await fetchJson(`/automation/executions/${selectedWorkflow.execution.id}/cancel`, { method: "POST" });
      setSelectedWorkflow((current) => ({ ...current, execution }));
      setAutomationStatus("cancelled");
    } catch (error) {
      setAutomationError(error.message);
      setAutomationStatus("error");
    }
  }

  async function saveWorkflow() {
    setAutomationError("");
    try {
      const payload = JSON.parse(workflowDraft);
      const path = editingWorkflowId ? `/automation/workflows/${editingWorkflowId}` : "/automation/workflows";
      const data = await fetchJson(path, { method: editingWorkflowId ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      setEditingWorkflowId(data.id);
      await loadWorkflows();
    } catch (error) {
      setAutomationError(error.message || "Enter valid workflow JSON.");
    }
  }

  function editWorkflow(workflow) {
    setEditingWorkflowId(workflow.id);
    setWorkflowDraft(JSON.stringify({ name: workflow.name, description: workflow.description, steps: workflow.steps }, null, 2));
  }

  async function deleteWorkflow(workflowId) {
    try {
      await fetchJson(`/automation/workflows/${workflowId}`, { method: "DELETE" });
      if (editingWorkflowId === workflowId) setEditingWorkflowId(null);
      await loadWorkflows();
    } catch (error) {
      setAutomationError(error.message);
    }
  }

  async function loadLearning() {
    try {
      setLearningError("");
      setLearning(await fetchJson("/learning/overview"));
    } catch (error) {
      setLearningError(error.message);
    }
  }

  async function recordLearningObservation(event) {
    event.preventDefault();
    if (!learningValue.trim()) return;
    try {
      await fetchJson("/learning/observations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kind: learningKind, value: learningValue.trim() }) });
      setLearningValue("");
      await loadLearning();
    } catch (error) {
      setLearningError(error.message);
    }
  }

  async function decideSuggestion(suggestionId, decision) {
    try {
      await fetchJson(`/learning/suggestions/${suggestionId}/${decision}`, { method: "POST" });
      await loadLearning();
      if (decision === "approve") await loadWorkflows();
    } catch (error) {
      setLearningError(error.message);
    }
  }

  const moduleCount = useMemo(() => health.modules.length, [health.modules]);

  async function sendFile(path, file) {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(`${API_BASE_URL}${path}`, { method: "POST", body: formData });
    const body = await response.json();
    if (!response.ok || !body.success) {
      throw new Error(body.detail ?? body.message ?? "The request failed.");
    }
    return body.data;
  }

  async function processDocument(file) {
    setAgentState("processing");
    setAgentError("");
    setDocumentResult(null);
    try {
      const result = await sendFile("/documents", file);
      setDocument(result);
      const summary = await fetchJson(`/documents/${result.id}/summarize`, { method: "POST" });
      setDocumentResult(summary);
      setAgentState("ready");
    } catch (error) {
      setAgentError(error.message);
      setAgentState("error");
    }
  }

  async function analyzeScreenshot(file) {
    setAgentState("processing");
    setAgentError("");
    try {
      const result = await sendFile("/vision/analyze", file);
      setVisionResult(result);
      setAgentState("ready");
    } catch (error) {
      setAgentError(error.message);
      setAgentState("error");
    }
  }

  async function askQuestion(event) {
    event.preventDefault();
    if (!document || !question.trim()) return;
    setAgentState("processing");
    try {
      const response = await fetch(`${API_BASE_URL}/documents/${document.id}/questions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question })
      });
      const body = await response.json();
      if (!response.ok || !body.success) throw new Error(body.detail ?? body.message);
      setDocumentResult((current) => ({ ...current, answer: body.data.answer, sources: body.data.sources }));
      setAgentState("ready");
    } catch (error) {
      setAgentError(error.message);
      setAgentState("error");
    }
  }

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

        <nav aria-label="Application navigation" className="flex gap-2">
          <button className={`rounded px-3 py-2 text-sm ${activeView === "dashboard" ? "bg-cyan-400 font-semibold text-slate-950" : "bg-white/10"}`} onClick={() => setActiveView("dashboard")} type="button">Dashboard</button>
          <button className={`rounded px-3 py-2 text-sm ${activeView === "plugins" ? "bg-cyan-400 font-semibold text-slate-950" : "bg-white/10"}`} onClick={() => setActiveView("plugins")} type="button">Plugin Manager</button>
          <button className={`rounded px-3 py-2 text-sm ${activeView === "productivity" ? "bg-cyan-400 font-semibold text-slate-950" : "bg-white/10"}`} onClick={() => setActiveView("productivity")} type="button">Productivity</button>
          <button className={`rounded px-3 py-2 text-sm ${activeView === "communication" ? "bg-cyan-400 font-semibold text-slate-950" : "bg-white/10"}`} onClick={() => setActiveView("communication")} type="button">Communication</button>
          <button className={`rounded px-3 py-2 text-sm ${activeView === "settings" ? "bg-cyan-400 font-semibold text-slate-950" : "bg-white/10"}`} onClick={() => setActiveView("settings")} type="button">Settings</button>
        </nav>

        {activeView === "dashboard" ? <>
        <section className="grid gap-4 md:grid-cols-4">
          <StatusTile label="Backend" value={health.status} />
          <StatusTile label="Environment" value={health.environment} />
          <StatusTile label="Default Model" value={health.default_model} />
          <StatusTile label="Foundation Modules" value={String(moduleCount)} />
        </section>

        <section className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
          <AssistantConsole />
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

          <section className="grid gap-6 lg:grid-cols-2">
            <UploadPanel
              title="Document Agent"
              description="Drop a PDF, Word, Excel, PowerPoint, text, or Markdown file to read, extract tables, and summarize it locally."
              accept=".pdf,.docx,.xlsx,.pptx,.txt,.md,.markdown"
              onFile={processDocument}
            />
            <UploadPanel
              title="Vision Agent"
              description="Drop a screenshot or image to run local OCR, recognize probable buttons, and surface visible errors."
              accept="image/*"
              onFile={analyzeScreenshot}
            />
          </section>

          {(agentState !== "idle" || agentError) && (
            <div className={`rounded-md border px-4 py-3 text-sm ${agentState === "error" ? "border-red-400/40 bg-red-500/10 text-red-200" : "border-cyan-400/30 bg-cyan-500/10 text-cyan-100"}`}>
              {agentError || `Vision & Document Agent: ${agentState}`}
            </div>
          )}

          <section className="grid gap-6 lg:grid-cols-2">
            <DocumentResult document={document} result={documentResult} question={question} onQuestionChange={setQuestion} onAsk={askQuestion} />
            <VisionResult result={visionResult} />
          </section>

          <AutomationPanel
            workflows={workflows}
            selectedWorkflow={selectedWorkflow}
            status={automationStatus}
            error={automationError}
            onLoad={loadWorkflows}
            onRun={runWorkflow}
            onCancel={cancelWorkflow}
            workflowDraft={workflowDraft}
            editingWorkflowId={editingWorkflowId}
            onDraftChange={setWorkflowDraft}
            onSave={saveWorkflow}
            onEdit={editWorkflow}
            onDelete={deleteWorkflow}
          />

          <LearningPanel learning={learning} kind={learningKind} value={learningValue} error={learningError} onKindChange={setLearningKind} onValueChange={setLearningValue} onLoad={loadLearning} onRecord={recordLearningObservation} onDecide={decideSuggestion} />

        </section>
        </> : activeView === "plugins" ? <PluginManager request={fetchJson} /> : activeView === "productivity" ? <ProductivityPlugins request={fetchJson} /> : activeView === "communication" ? <CommunicationPlugins request={fetchJson} /> : <SettingsPanel request={fetchJson} />}
      </section>
    </main>
  );
}

function LearningPanel({ learning, kind, value, error, onKindChange, onValueChange, onLoad, onRecord, onDecide }) {
  return (
    <section className="rounded-md border border-white/10 bg-white/[0.04] p-5">
      <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-lg font-semibold">Learning Mode</h2><p className="mt-1 text-sm text-slate-300">Learn repeated habits locally. Suggestions never create automation without your approval.</p></div><button className="rounded border border-white/15 bg-black/20 px-3 py-2 text-sm" onClick={onLoad} type="button">Load learning</button></div>
      <form className="mt-4 flex flex-wrap gap-2" onSubmit={onRecord}>
        <select aria-label="Observation kind" className="rounded border border-white/15 bg-black/20 px-3 py-2 text-sm" value={kind} onChange={(event) => onKindChange(event.target.value)}>{["application", "browser", "folder", "coding_style", "repository", "command", "startup"].map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}</select>
        <input aria-label="Habit value" className="min-w-48 flex-1 rounded border border-white/15 bg-black/20 px-3 py-2 text-sm" value={value} onChange={(event) => onValueChange(event.target.value)} placeholder="Record a local habit" />
        <button className="rounded bg-cyan-400 px-3 py-2 text-sm font-semibold text-slate-950" type="submit">Record</button>
      </form>
      {error && <p className="mt-3 text-sm text-red-200">{error}</p>}
      {!learning ? <p className="mt-4 text-sm text-slate-400">Load learning to see local preferences and recommendations.</p> : <div className="mt-4 grid gap-5 lg:grid-cols-2"><div><h3 className="font-medium">Learned preferences ({learning.observation_count} signals)</h3>{learning.preferences.length === 0 ? <p className="mt-2 text-sm text-slate-400">No preferences inferred yet.</p> : <ul className="mt-2 space-y-2 text-sm">{learning.preferences.map((item) => <li className="rounded bg-black/20 px-3 py-2" key={item.key}>{item.key.replaceAll("_", " ")}: <span className="text-cyan-100">{item.value}</span> ({item.occurrences})</li>)}</ul>}</div><div><h3 className="font-medium">Automation suggestions</h3>{learning.suggestions.length === 0 ? <p className="mt-2 text-sm text-slate-400">No repeated routine found yet.</p> : <div className="mt-2 space-y-2">{learning.suggestions.map((suggestion) => <article className="rounded bg-black/20 p-3 text-sm" key={suggestion.id}><p className="font-medium">{suggestion.title}</p><p className="mt-1 text-slate-300">{suggestion.description}</p><p className="mt-1 text-xs text-slate-400">{suggestion.occurrences} repeated observations · {suggestion.status}</p>{suggestion.status === "pending" && <div className="mt-2 flex gap-3"><button className="text-cyan-200" onClick={() => onDecide(suggestion.id, "approve")} type="button">Approve</button><button className="text-red-200" onClick={() => onDecide(suggestion.id, "dismiss")} type="button">Dismiss</button></div>}</article>)}</div>}</div></div>}
    </section>
  );
}

function AutomationPanel({ workflows, selectedWorkflow, status, error, onLoad, onRun, onCancel, workflowDraft, editingWorkflowId, onDraftChange, onSave, onEdit, onDelete }) {
  return (
    <section className="rounded-md border border-white/10 bg-white/[0.04] p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Automation & Planner</h2>
          <p className="mt-1 text-sm text-slate-300">Run safe local workflows with visible dependency-aware progress.</p>
        </div>
        <button className="rounded border border-white/15 bg-black/20 px-3 py-2 text-sm" onClick={onLoad} type="button">Load workflows</button>
      </div>
      {error && <p className="mt-4 text-sm text-red-200">{error}</p>}
      {workflows.length === 0 ? <p className="mt-4 text-sm text-slate-400">Load a workflow to begin.</p> : <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {workflows.map((workflow) => <article className="rounded border border-white/10 bg-black/20 p-3" key={workflow.id}>
          <h3 className="font-medium">{workflow.name}</h3>
          <p className="mt-1 min-h-10 text-xs leading-5 text-slate-400">{workflow.description}</p>
          <button className="mt-3 rounded bg-cyan-400 px-3 py-2 text-xs font-semibold text-slate-950" onClick={() => onRun(workflow)} type="button">Run workflow</button>
          {workflow.source === "custom" && <div className="mt-2 flex gap-2"><button className="text-xs text-cyan-200" onClick={() => onEdit(workflow)} type="button">Edit</button><button className="text-xs text-red-200" onClick={() => onDelete(workflow.id)} type="button">Delete</button></div>}
        </article>)}
      </div>}
      {selectedWorkflow?.execution && <div className="mt-5 flex flex-wrap items-center gap-3 rounded border border-cyan-300/20 bg-cyan-500/10 p-3 text-sm text-cyan-100">
        <span>{selectedWorkflow.name}: {status} ({selectedWorkflow.execution.progress_percent}%)</span>
        {status === "running" && <button className="rounded border border-cyan-200/30 px-2 py-1 text-xs" onClick={onCancel} type="button">Cancel</button>}
      </div>}
      <div className="mt-6 border-t border-white/10 pt-5">
        <h3 className="font-medium">{editingWorkflowId ? "Edit custom workflow" : "Record custom workflow"}</h3>
        <p className="mt-1 text-xs text-slate-400">Use safe `notify` or `wait` steps. Each step needs an id, title, action, and action-specific message or duration_seconds.</p>
        <textarea className="mt-3 min-h-48 w-full rounded border border-white/15 bg-black/20 p-3 font-mono text-xs" value={workflowDraft} onChange={(event) => onDraftChange(event.target.value)} aria-label="Custom workflow definition" />
        <button className="mt-3 rounded bg-white/10 px-3 py-2 text-sm" onClick={onSave} type="button">{editingWorkflowId ? "Save changes" : "Save workflow"}</button>
      </div>
    </section>
  );
}

function UploadPanel({ title, description, accept, onFile }) {
  const [dragging, setDragging] = useState(false);

  function selectFile(file) {
    if (file) onFile(file);
  }

  return (
    <label
      className={`cursor-pointer rounded-md border border-dashed p-6 transition ${dragging ? "border-cyan-300 bg-cyan-300/10" : "border-white/20 bg-white/[0.04] hover:border-white/40"}`}
      onDragEnter={() => setDragging(true)}
      onDragLeave={() => setDragging(false)}
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        selectFile(event.dataTransfer.files[0]);
      }}
    >
      <input className="sr-only" type="file" accept={accept} onChange={(event) => selectFile(event.target.files[0])} />
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-2 text-sm leading-6 text-slate-300">{description}</p>
      <span className="mt-5 inline-block rounded bg-white/10 px-3 py-2 text-xs font-medium text-cyan-100">Choose file or drop it here</span>
    </label>
  );
}

function DocumentResult({ document, result, question, onQuestionChange, onAsk }) {
  return (
    <div className="min-h-64 rounded-md border border-white/10 bg-white/[0.04] p-5">
      <h2 className="text-lg font-semibold">Document workspace</h2>
      {!document ? <p className="mt-4 text-sm text-slate-400">Upload a document to begin.</p> : <>
        <p className="mt-3 text-sm text-cyan-100">{document.filename} · {document.document_type.toUpperCase()} · {document.tables.length} table(s)</p>
        {result?.summary && <p className="mt-4 whitespace-pre-wrap text-sm leading-6 text-slate-200">{result.summary}</p>}
        {result?.answer && <div className="mt-4 rounded bg-black/20 p-3 text-sm text-slate-200">{result.answer}</div>}
        <form className="mt-5 flex gap-2" onSubmit={onAsk}>
          <input className="min-w-0 flex-1 rounded border border-white/15 bg-black/20 px-3 py-2 text-sm" value={question} onChange={(event) => onQuestionChange(event.target.value)} placeholder="Ask about this document" />
          <button className="rounded bg-cyan-400 px-3 py-2 text-sm font-semibold text-slate-950" type="submit">Ask</button>
        </form>
      </>}
    </div>
  );
}

function VisionResult({ result }) {
  return (
    <div className="min-h-64 rounded-md border border-white/10 bg-white/[0.04] p-5">
      <h2 className="text-lg font-semibold">Screenshot understanding</h2>
      {!result ? <p className="mt-4 text-sm text-slate-400">Upload a screenshot to inspect it locally.</p> : <>
        <p className="mt-3 text-sm text-cyan-100">{result.summary}</p>
        {result.errors.length > 0 && <p className="mt-3 text-sm text-amber-200">Possible errors: {result.errors.join(" · ")}</p>}
        {result.ui_elements.length > 0 && <p className="mt-3 text-sm text-slate-300">Buttons: {result.ui_elements.map((element) => element.label).join(", ")}</p>}
        <pre className="mt-4 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-black/20 p-3 text-xs text-slate-300">{result.text || "No text detected."}</pre>
      </>}
    </div>
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

function AssistantConsole() {
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState([]);
  const [state, setState] = useState("Voice checking");
  const [listening, setListening] = useState(false);
  const runtime = useRef(null);
  const speechRequest = useRef(0);
  useEffect(() => {
    let active = true;
    const voice = createVoiceRuntime();
    runtime.current = voice;
    void voice.start().then(async () => {
      if (!active) { await voice.stop(); return; }
    }).catch((error) => {
      if (active && runtime.current === voice) {
        setListening(false);
        setState(error.message);
      }
    });
    return () => {
      active = false;
      if (runtime.current === voice) runtime.current = null;
      void voice.stop();
    };
  }, []);
  function createVoiceRuntime() {
    let voice;
    voice = new VoiceRuntime({
      apiBaseUrl: API_BASE_URL,
      onCommand: (message, onVoicePhase) => send(message, { voice: true, onVoicePhase }),
      onWake: async () => {
        const response = await fetch(`${API_BASE_URL}/voice/speak?wait=true`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: "Yes, Boss." }) });
        if (!response.ok) throw new Error("Wake acknowledgement TTS failed.");
      },
      onState: (nextState) => {
        if (runtime.current !== voice) return;
        setListening(voice.listeningEnabled);
        setState(nextState);
      },
      onInterruption: () => { if (!runtime.current?.capturePaused) void fetch(`${API_BASE_URL}/voice/speak`, { method: "DELETE" }); }
    });
    return voice;
  }
  async function send(message, { voice = false, onVoicePhase } = {}) {
    if (!message.trim()) return;
    setMessages((current) => [...current, { role: "You", text: message }, { role: "Mjolnir", text: "…" }]); setDraft("");
    try {
      const response = await fetch(`${API_BASE_URL}/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message, history: [] }) });
      const reader = response.body?.getReader(); const decoder = new TextDecoder(); let answer = "";
      while (reader) { const { done, value } = await reader.read(); if (done) break; decoder.decode(value).split("\n").filter(Boolean).forEach((line) => { const event = JSON.parse(line); if (event.type === "token") answer += event.content; }); }
      const addressedAnswer = addressBoss(answer || "No response received.");
      setMessages((current) => [...current.slice(0, -1), { role: "Mjolnir", text: addressedAnswer }]);
      {
        onVoicePhase?.("TOOL_COMPLETION", { response_length: addressedAnswer.length });
        onVoicePhase?.("TTS_START", { utterance: "command_response" });
        const requestId = ++speechRequest.current;
        runtime.current?.beginPlayback("assistant_reply_tts");
        try {
          const spokenText = addressedAnswer;
          const speech = await fetch(`${API_BASE_URL}/voice/speak?wait=true`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: spokenText }) });
          if (!speech.ok) {
            const failure = await speech.json().catch(() => ({}));
            throw new Error(failure.detail ?? "Assistant reply TTS failed.");
          }
        } catch (error) {
          onVoicePhase?.("TTS_FAILURE", { error: error.message });
          if (requestId === speechRequest.current) setState(`Speech failed: ${error.message}`);
          // Speech is an output channel, not the source of the answer. Keep
          // the successfully generated chat response visible if audio fails.
        } finally {
          runtime.current?.endPlayback("assistant_reply_tts_complete");
          onVoicePhase?.("TTS_END", { utterance: "command_response" });
        }
      }
    } catch (error) { setMessages((current) => [...current.slice(0, -1), { role: "Mjolnir", text: error.message }]); }
  }
  async function toggleVoice() {
    try {
      if (runtime.current?.listeningEnabled) { await runtime.current.pause(); return; }
      if (!runtime.current) runtime.current = createVoiceRuntime();
      await runtime.current.resume();
    } catch (error) {
      setListening(Boolean(runtime.current?.listeningEnabled));
      setState(error.message);
    }
  }
  return <section className="rounded-md border border-cyan-400/30 bg-black/20 p-5 lg:col-span-2"><div className="flex items-center justify-between gap-3"><div><h2 className="text-lg font-semibold">Voice Assistant</h2><p className="text-sm text-cyan-100">{state}</p></div><button className="rounded bg-cyan-400 px-3 py-2 text-sm font-semibold text-slate-950" type="button" onClick={toggleVoice}>{listening ? "Pause Listening" : "Resume Listening"}</button></div><div className="mt-4 max-h-48 space-y-2 overflow-auto text-sm">{messages.map((item, index) => <p key={index}><strong>{item.role}:</strong> {item.text}</p>)}</div><form className="mt-4 flex gap-2" onSubmit={(event) => { event.preventDefault(); void send(draft); }}><input className="min-w-0 flex-1 rounded border border-white/20 bg-black/30 px-3 py-2" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Type a command or say Mjolnir"/><button className="rounded border border-white/20 px-3 py-2" type="submit">Send</button></form></section>;
}

function addressBoss(reply) {
  if (/\bboss\b/i.test(reply)) return reply;
  const trimmed = reply.trim();
  if (!trimmed) return trimmed;
  return `${trimmed.replace(/[.!?]+$/, "")}, Boss.`;
}
