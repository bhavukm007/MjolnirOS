import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";

let voiceOptions;

vi.mock("./voice_runtime.js", () => ({
  VoiceRuntime: class {
    constructor(options) {
      voiceOptions = options;
    }

    async start() {
      voiceOptions.onCommand("Mjolnir, open terminal.");
    }

    async stop() {}
  }
}));

import { ChatWorkspace } from "./App.jsx";


test("voice commands are forwarded to the Coding Agent chat route", async () => {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode('{"type":"token","content":"VS Code integrated terminal opened."}\n{"type":"done"}\n'));
      controller.close();
    }
  });
  global.fetch = vi.fn((url) => {
    if (url.endsWith("/voice/health")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, data: { available: true, wake_word: "Mjolnir" } }) });
    }
    if (url.endsWith("/chat")) {
      return Promise.resolve({ ok: true, body: stream });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, data: {} }) });
  });

  render(<ChatWorkspace aiHealth={{ available: true, message: "ready" }} defaultModel="qwen2.5:3b" models={[{ name: "qwen2.5:3b" }]} />);

  fireEvent.click(await screen.findByLabelText("Start voice listening"));
  await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
    "http://127.0.0.1:8000/api/v1/chat",
    expect.objectContaining({ body: expect.stringContaining("Mjolnir, open terminal.") })
  ));
  expect(await screen.findByText("VS Code integrated terminal opened.")).toBeInTheDocument();
});
