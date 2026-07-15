import { Canvas } from "@react-three/fiber";
import { useMemo } from "react";
import * as THREE from "three";

import MjolnirCoreScene from "./MjolnirCoreScene.jsx";

export default function MjolnirCoreCanvas({ audioLevel, reducedMotion, state, suspended }) {
  const quality = useMemo(() => detectQuality(reducedMotion), [reducedMotion]);

  return (
    <Canvas
      camera={{ fov: 34, near: 0.1, far: 70, position: [0.15, 0.45, 9.35] }}
      className="core-canvas"
      dpr={[1, quality.dpr]}
      frameloop={suspended ? "demand" : "always"}
      gl={{
        alpha: true,
        antialias: quality.antialias,
        depth: true,
        failIfMajorPerformanceCaveat: false,
        powerPreference: "high-performance",
        premultipliedAlpha: false,
        stencil: false
      }}
      onCreated={({ gl }) => {
        gl.setClearColor(0x02050a, 0);
        gl.outputColorSpace = THREE.SRGBColorSpace;
        gl.toneMapping = THREE.ACESFilmicToneMapping;
        gl.toneMappingExposure = 0.78;
      }}
    >
      <MjolnirCoreScene
        audioLevel={audioLevel}
        quality={quality}
        reducedMotion={reducedMotion}
        state={state}
        suspended={suspended}
      />
    </Canvas>
  );
}

function detectQuality(reducedMotion) {
  if (reducedMotion) {
    return { routeCount: 34, packetCount: 34, nodeCount: 52, dpr: 1, antialias: false, multisampling: 0 };
  }

  const cores = navigator.hardwareConcurrency || 4;
  const memory = navigator.deviceMemory || 4;
  const lowPower = cores <= 4 || memory <= 4;
  return lowPower
    ? { routeCount: 48, packetCount: 58, nodeCount: 82, dpr: 1.2, antialias: false, multisampling: 0 }
    : { routeCount: 76, packetCount: 104, nodeCount: 142, dpr: 1.45, antialias: true, multisampling: 2 };
}
