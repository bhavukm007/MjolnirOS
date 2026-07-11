import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import App, { SettingsScreen } from "./App.jsx";

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
});
