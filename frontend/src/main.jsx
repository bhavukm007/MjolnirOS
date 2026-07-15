import React from "react";
import { createRoot } from "react-dom/client";

import App from "./App.jsx";
import { AssistantStateProvider } from "./state/AssistantStateProvider.jsx";
import "./styles.css";

const savedTheme = window.localStorage?.getItem("mjolnir.theme") || "dark";
document.documentElement.dataset.theme = savedTheme === "system" ? (window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark") : savedTheme;

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AssistantStateProvider><App /></AssistantStateProvider>
  </React.StrictMode>
);
