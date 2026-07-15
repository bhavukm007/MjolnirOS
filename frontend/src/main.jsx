import React from "react";
import { createRoot } from "react-dom/client";

import App from "./App.jsx";
import { AssistantStateProvider } from "./state/AssistantStateProvider.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AssistantStateProvider><App /></AssistantStateProvider>
  </React.StrictMode>
);
