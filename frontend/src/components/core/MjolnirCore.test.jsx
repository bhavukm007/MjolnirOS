import { render, screen } from "@testing-library/react";
import { useEffect } from "react";
import { describe, expect, test } from "vitest";

import { AssistantStateProvider, useAssistantState } from "../../state/AssistantStateProvider.jsx";
import MjolnirCore from "./MjolnirCore.jsx";

function StateDriver({ state }) {
  const { setState } = useAssistantState();
  useEffect(() => setState(state), [setState, state]);
  return <MjolnirCore />;
}

describe("MjolnirCore", () => {
  test("exposes assistant state changes accessibly", async () => {
    const { rerender } = render(<AssistantStateProvider><StateDriver state="listening" /></AssistantStateProvider>);
    expect(await screen.findByRole("img", { name: "Mjolnir Core: Listening" })).toBeInTheDocument();
    rerender(<AssistantStateProvider><StateDriver state="speaking" /></AssistantStateProvider>);
    expect(await screen.findByRole("img", { name: "Mjolnir Core: Speaking" })).toBeInTheDocument();
  });

  test("offline connection overrides the animated state", () => {
    const { container } = render(<AssistantStateProvider><MjolnirCore connectionState="offline" /></AssistantStateProvider>);
    expect(screen.getByRole("img", { name: "Mjolnir Core: Offline" })).toHaveClass("mjolnir-core--offline");
    expect(container.querySelector(".core-render-fallback")).toBeInTheDocument();
    expect(container.querySelector("svg")).not.toBeInTheDocument();
  });
});
