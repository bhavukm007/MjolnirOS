import { Component, lazy, Suspense, useMemo } from "react";
import { motion, useReducedMotion } from "framer-motion";

import { useAssistantState } from "../../state/AssistantStateProvider.jsx";

const MjolnirCoreCanvas = lazy(() => import("./MjolnirCoreCanvas.jsx"));

const stateLabels = {
  idle: "Ready",
  "wake-word": "Awake",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  "executing-tool": "Executing",
  success: "Complete",
  error: "Attention",
  paused: "Paused",
  offline: "Offline"
};

export default function MjolnirCore({ connectionState = "online", className = "" }) {
  const { state, audioLevel, suspended } = useAssistantState();
  const reducedMotion = useReducedMotion();
  const visibleState = connectionState === "offline" ? "offline" : state;
  const webglAvailable = useMemo(() => supportsWebGL(), []);

  return (
    <motion.div
      animate={{ opacity: visibleState === "offline" ? 0.62 : 1 }}
      aria-label={`Mjolnir Core: ${stateLabels[visibleState]}`}
      className={`mjolnir-core mjolnir-core--${visibleState} ${suspended ? "is-suspended" : ""} ${className}`}
      role="img"
      transition={{ duration: 0.8, ease: [0.2, 0.75, 0.2, 1] }}
    >
      <div className="core-environment" aria-hidden="true" />
      <div className="core-atmosphere" aria-hidden="true" />
      {webglAvailable ? (
        <CoreRenderBoundary fallback={<CoreFallback />}>
          <Suspense fallback={<CoreFallback />}>
            <MjolnirCoreCanvas
              audioLevel={audioLevel}
              reducedMotion={Boolean(reducedMotion)}
              state={visibleState}
              suspended={suspended}
            />
          </Suspense>
        </CoreRenderBoundary>
      ) : <CoreFallback />}
      <div className="core-state-label">
        <i />
        <span>{stateLabels[visibleState]}</span>
        <small>Local intelligence core</small>
      </div>
    </motion.div>
  );
}

class CoreRenderBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error) {
    console.error("[mjolnir-core] WebGL renderer failed; using the safe fallback.", error);
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

function CoreFallback() {
  return (
    <div className="core-render-fallback" aria-hidden="true">
      <span className="core-render-fallback__field" />
      <span className="core-render-fallback__network" />
      <span className="core-render-fallback__nucleus" />
    </div>
  );
}

function supportsWebGL() {
  if (typeof window === "undefined") return false;
  return Boolean(window.WebGL2RenderingContext || window.WebGLRenderingContext);
}
