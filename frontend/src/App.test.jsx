import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import App from "./App.jsx";

describe("App", () => {
  test("renders dashboard data from the backend", async () => {
    global.fetch = vi.fn((url) => {
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
    expect(screen.getByText("Document Agent")).toBeInTheDocument();
    expect(screen.getByText("Vision Agent")).toBeInTheDocument();
    expect(screen.getByText("Automation & Planner")).toBeInTheDocument();
    expect(screen.getByText("Learning Mode")).toBeInTheDocument();
    expect(screen.getByText("Plugin Marketplace")).toBeInTheDocument();
  });
});
