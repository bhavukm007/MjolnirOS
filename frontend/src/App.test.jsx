import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import App from "./App.jsx";

describe("App", () => {
  test("renders dashboard data from the backend", async () => {
    global.fetch = vi.fn((url) => {
      if (url.endsWith("/chat")) {
        const read = vi.fn()
          .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode('{"type":"token","content":"Done."}\n') })
          .mockResolvedValueOnce({ done: true, value: undefined });
        return Promise.resolve({ ok: true, body: { getReader: () => ({ read }) } });
      }
      const data = url.endsWith("/health")
        ? {
            status: "ok",
            app_name: "MjolnirOS",
            environment: "test",
            version: "0.1.0",
            default_model: "qwen2.5:3b",
            modules: ["backend", "frontend"]
          }
        : url.endsWith("/automation/workflows")
          ? []
          : url.includes("/plugins/categories")
            ? ["Utilities"]
            : url.includes("/plugins/marketplace")
              ? [{ manifest: { id: "calculator", name: "Calculator", version: "1.0.0", description: "Local calculations.", category: "Utilities" }, permissions: [], installed: true, update_available: false }]
          : url.includes("/plugins")
            ? [{ manifest: { id: "calculator", name: "Calculator", version: "1.0.0", description: "Local calculations.", category: "Utilities" }, permissions: [], status: "disabled", blocked_reason: null }]
            : url.includes("/productivity/connections")
              ? [{ provider: "google", connected: true, account_email: "user@example.com", expires_at: null, last_sync_at: null, error: null }, { provider: "notion", connected: false, account_email: null, expires_at: null, last_sync_at: null, error: null }]
          : {
            app_name: "MjolnirOS",
            environment: "test",
            api_prefix: "/api/v1",
            default_model: "qwen2.5:3b",
            enabled_foundation_modules: ["backend", "frontend"]
          };

      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ success: true, message: "ok", data })
      });
    });

    render(<App />);

    await waitFor(() => expect(screen.getByText("online")).toBeInTheDocument());
    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/voice/sessions"),
      { method: "POST" }
    ));
    expect(screen.getByText("MjolnirOS")).toBeInTheDocument();
    expect(screen.getByText("backend")).toBeInTheDocument();
    expect(screen.getByText("frontend")).toBeInTheDocument();
    expect(screen.getByText("Document Agent")).toBeInTheDocument();
    expect(screen.getByText("Vision Agent")).toBeInTheDocument();
    expect(screen.getByText("Automation & Planner")).toBeInTheDocument();
    expect(screen.getByText("Learning Mode")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Plugin Manager" }));
    await waitFor(() => expect(screen.getByText("Installed plugins")).toBeInTheDocument());
    expect(screen.getByText("Calculator")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Load / Enable" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Marketplace" }));
    expect(screen.getByText("Marketplace")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Load / Enable" }));
    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining("/plugins/calculator/load"), { method: "POST" }));

    fireEvent.click(screen.getByRole("button", { name: "Productivity" }));
    await waitFor(() => expect(screen.getByText("Productivity Plugins")).toBeInTheDocument());
    expect(screen.getByText("Connected: user@example.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sync" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Dashboard" }));
    expect(global.fetch.mock.calls.filter(([url, options]) => url.includes("/voice/sessions") && options?.method === "POST")).toHaveLength(1);
    fireEvent.change(screen.getByPlaceholderText("Type a command or say Mjolnir"), { target: { value: "typed command" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(screen.getByText("Done, Boss.")).toBeInTheDocument());
    expect(global.fetch.mock.calls.some(([url]) => url.includes("/voice/speak?wait=true"))).toBe(true);
  });
});
