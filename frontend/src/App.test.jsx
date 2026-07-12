import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import App, { ChatWorkspace, SettingsScreen } from "./App.jsx";

describe("App", () => {
  test("renders dashboard data from the backend", async () => {
    global.fetch = vi.fn((url) => {
      const data = url.endsWith("/ai/health")
        ? {
            available: true,
            default_model: "qwen2.5:3b",
            default_model_available: true,
            message: "Local Ollama runtime is ready."
          }
        : url.endsWith("/ai/models")
          ? {
              available: true,
              models: [{ name: "qwen2.5:3b" }]
            }
          : url.endsWith("/health")
        ? {
            status: "ok",
            app_name: "MjolnirOS",
            environment: "test",
            version: "0.1.0",
            default_model: "qwen2.5:3b",
            modules: ["backend", "frontend"]
          }
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
    expect(screen.getByText("MjolnirOS")).toBeInTheDocument();
    expect(screen.getByText("backend")).toBeInTheDocument();
    expect(screen.getByText("frontend")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Local AI" })).toBeInTheDocument();
    expect(screen.getByLabelText("Local model")).toHaveValue("qwen2.5:3b");
  });

  test("saves the Windows startup preference from desktop settings", async () => {
    const setLaunchOnStartup = vi.fn(() => Promise.resolve({ launchOnStartup: true }));
    Object.defineProperty(window, "mjolniros", {
      configurable: true,
      value: {
        desktop: {
          getSettings: () => Promise.resolve({ launchOnStartup: false }),
          setLaunchOnStartup,
          openMainWindow: vi.fn()
        }
      }
    });

    render(<SettingsScreen />);

    const startupToggle = await screen.findByLabelText("Launch MjolnirOS when Windows starts");
    expect(startupToggle).not.toBeChecked();
    fireEvent.click(startupToggle);

    await waitFor(() => expect(setLaunchOnStartup).toHaveBeenCalledWith(true));
    expect(await screen.findByText("Windows startup is enabled.")).toBeInTheDocument();
  });

  test("renders streamed local AI tokens in the conversation", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('{"type":"token","content":"Hello"}\n'));
        controller.enqueue(encoder.encode('{"type":"token","content":" from Ollama"}\n{"type":"done"}\n'));
        controller.close();
      }
    });
    global.fetch = vi.fn(() => Promise.resolve({ ok: true, body: stream }));

    render(
      <ChatWorkspace
        aiHealth={{ available: true, message: "Local Ollama runtime is ready." }}
        defaultModel="qwen2.5:3b"
        models={[{ name: "qwen2.5:3b" }]}
      />
    );

    fireEvent.change(screen.getByLabelText("Message Ollama"), { target: { value: "Hello" } });
    fireEvent.click(screen.getByLabelText("Send message"));

    expect(await screen.findByText("Hello from Ollama")).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/v1/chat",
      expect.objectContaining({ method: "POST" })
    );
  });
});
