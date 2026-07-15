import { Bloom, EffectComposer } from "@react-three/postprocessing";
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import {
  createOrbitParticles,
  createPacketDescriptors,
  createSphereHaze,
  createSphereNetwork,
  createSphereNodes,
  createSurfaceNetwork
} from "./coreGeometry.js";

const STATE_PROFILES = {
  idle: { activity: 0.86, energy: 0.9, flow: 0.9, speed: 0.8, color: "#21a9ee", secondary: "#55ddff" },
  "wake-word": { activity: 1.12, energy: 1.16, flow: 1.08, speed: 1.08, color: "#35c9ff", secondary: "#e5fbff" },
  listening: { activity: 1.02, energy: 1.02, flow: 0.94, speed: 0.86, color: "#35c8f5", secondary: "#e0faff" },
  thinking: { activity: 1.28, energy: 1.12, flow: 1.52, speed: 1.24, color: "#248fd8", secondary: "#68e3ff" },
  speaking: { activity: 1.08, energy: 1.08, flow: 1.04, speed: 0.92, color: "#3bd3ff", secondary: "#edfdff" },
  "executing-tool": { activity: 1.3, energy: 1.18, flow: 1.68, speed: 1.36, color: "#279ee8", secondary: "#9deeff" },
  success: { activity: 1.12, energy: 1.2, flow: 1.06, speed: 0.9, color: "#50dcff", secondary: "#f2feff" },
  error: { activity: 0.92, energy: 0.88, flow: 1.3, speed: 1.12, color: "#197bb8", secondary: "#7ddfff" },
  paused: { activity: 0.64, energy: 0.68, flow: 0.62, speed: 0.58, color: "#198fc7", secondary: "#55cdeb" },
  offline: { activity: 0.08, energy: 0.24, flow: 0.045, speed: 0.02, color: "#183b52", secondary: "#355c70" }
};

const CLUSTER_POSITIONS = [
  [-1.18, 0.9, 0.4],
  [1.02, 1.02, -0.48],
  [-1.3, -0.5, -0.38],
  [1.2, -0.72, 0.48],
  [0.14, 0.42, 1.34],
  [-0.24, -1.14, -0.8],
  [0.58, -0.1, -1.34]
];

const routeVertexShader = `
  attribute float aProgress;
  attribute float aPhase;
  attribute float aWeight;
  uniform float uTime;
  uniform float uActivity;
  varying float vProgress;
  varying float vPhase;
  varying float vWeight;
  void main() {
    vProgress = aProgress;
    vPhase = aPhase;
    vWeight = aWeight;
    vec3 p = position;
    float radius = length(p);
    float anchored = sin(aProgress * 3.14159265);
    float interior = 1.0 - smoothstep(1.72, 2.08, radius);
    vec3 direction = normalize(p + vec3(0.0001));
    vec3 fieldAxis = normalize(vec3(
      sin(aPhase * 1.31 + uTime * 0.031),
      cos(aPhase * 0.87 - uTime * 0.027),
      sin(aPhase * 1.73 + 1.2)
    ));
    vec3 tangent = normalize(cross(direction, fieldAxis) + vec3(0.0001));
    float neuralFlow = sin(aProgress * 12.0 + aPhase + uTime * 0.16)
      + sin(aProgress * 5.0 - aPhase * 0.7 - uTime * 0.11) * 0.46;
    p += tangent * neuralFlow * anchored * interior * (0.018 + uActivity * 0.012);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
  }
`;

const routeFragmentShader = `
  uniform float uTime;
  uniform float uActivity;
  uniform float uAudio;
  uniform float uOpacity;
  uniform float uSync;
  uniform vec3 uColor;
  uniform vec3 uSecondary;
  varying float vProgress;
  varying float vPhase;
  varying float vWeight;
  void main() {
    float forward = pow(0.5 + 0.5 * sin(vProgress * 38.0 - uTime * (2.0 + vWeight) + vPhase), 16.0);
    float reverse = pow(0.5 + 0.5 * sin(vProgress * 17.0 + uTime * 1.12 + vPhase * 1.6), 23.0);
    float branchSignal = pow(0.5 + 0.5 * sin(vProgress * 61.0 - uTime * 1.54 + vPhase * 2.3), 34.0);
    float synchronization = pow(0.5 + 0.5 * sin(vProgress * 9.0 - uTime * 2.8 + vPhase), 28.0) * uSync;
    float formationWave = 0.5 + 0.5 * sin(vProgress * 5.5 + vPhase * 1.4 + uTime * 0.12);
    float formation = 0.76 + smoothstep(0.18, 0.78, formationWave) * 0.24;
    float signal = (forward * (0.68 + uActivity * 0.74) + reverse * 0.42 + branchSignal * 0.66 + synchronization * 1.18 + uAudio * forward * 0.7) * formation;
    float endpointGlow = pow(1.0 - min(vProgress, 1.0 - vProgress) * 2.0, 7.0);
    float base = (0.052 + pow(vWeight, 2.4) * 0.19 + endpointGlow * 0.044) * uOpacity * formation;
    float intensity = base + signal * uOpacity;
    vec3 color = mix(uColor, uSecondary, clamp(forward * 0.84 + reverse * 0.3 + synchronization, 0.0, 1.0));
    gl_FragColor = vec4(color * (0.5 + intensity * 1.25), clamp(intensity * 0.8, 0.0, 0.72));
  }
`;

const pointVertexShader = `
  attribute float aPhase;
  attribute float aSize;
  uniform float uTime;
  uniform float uActivity;
  varying float vPulse;
  void main() {
    vec3 p = position;
    vec3 direction = normalize(p + vec3(0.0001));
    vec3 tangent = normalize(cross(direction, normalize(vec3(0.31, 0.77, 0.55))) + vec3(0.0001));
    p += tangent * sin(uTime * 0.12 + aPhase) * 0.018 * uActivity;
    vec4 mvPosition = modelViewMatrix * vec4(p, 1.0);
    vPulse = 0.58 + 0.42 * sin(uTime * (0.68 + aPhase * 0.035) + aPhase);
    gl_PointSize = aSize * (1.0 + vPulse * uActivity * 0.42) * (94.0 / max(1.0, -mvPosition.z));
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const pointFragmentShader = `
  uniform float uEnergy;
  uniform vec3 uColor;
  uniform vec3 uSecondary;
  varying float vPulse;
  void main() {
    vec2 centered = gl_PointCoord - vec2(0.5);
    float d = length(centered) * 2.0;
    float core = 1.0 - smoothstep(0.0, 0.28, d);
    float glow = 1.0 - smoothstep(0.08, 1.0, d);
    float alpha = (core + glow * 0.4) * (0.3 + vPulse * 0.56) * uEnergy;
    vec3 color = mix(uColor, uSecondary, core * 0.8);
    gl_FragColor = vec4(color * (0.72 + core * 1.8), alpha);
  }
`;

const hazeVertexShader = `
  attribute float aPhase;
  attribute float aSize;
  uniform float uTime;
  uniform float uActivity;
  varying float vEnergy;
  void main() {
    vec3 displaced = position;
    displaced += normalize(position + vec3(0.001)) * sin(uTime * 0.11 + aPhase) * 0.025 * uActivity;
    vec4 mvPosition = modelViewMatrix * vec4(displaced, 1.0);
    vEnergy = 0.62 + 0.38 * sin(uTime * 0.29 + aPhase);
    gl_PointSize = aSize * (104.0 / max(1.0, -mvPosition.z));
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const hazeFragmentShader = `
  uniform float uEnergy;
  uniform vec3 uColor;
  varying float vEnergy;
  void main() {
    vec2 centered = gl_PointCoord - vec2(0.5);
    float radius = dot(centered, centered) * 4.0;
    float falloff = pow(max(0.0, 1.0 - radius), 3.2);
    gl_FragColor = vec4(uColor * (0.44 + vEnergy * 0.34), falloff * 0.07 * uEnergy);
  }
`;

const shellVertexShader = `
  uniform float uTime;
  uniform float uActivity;
  varying vec3 vNormal;
  varying vec3 vWorldPosition;
  void main() {
    vec3 p = position;
    float rippleA = sin(p.x * 3.1 + p.y * 2.3 + uTime * 0.085);
    float rippleB = sin(p.z * 3.7 - p.y * 2.6 - uTime * 0.067);
    float deformation = (rippleA + rippleB * 0.62) * (0.008 + uActivity * 0.0035);
    p += normal * deformation;
    vNormal = normalize(normalMatrix * normal);
    vWorldPosition = p;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
  }
`;

const shellFragmentShader = `
  uniform float uTime;
  uniform float uActivity;
  uniform float uOpacity;
  uniform vec3 uColor;
  uniform vec3 uSecondary;
  varying vec3 vNormal;
  varying vec3 vWorldPosition;
  void main() {
    float fresnel = pow(1.0 - abs(dot(normalize(vNormal), vec3(0.0, 0.0, 1.0))), 3.1);
    vec3 p = normalize(vWorldPosition);
    float latitude = pow(0.5 + 0.5 * sin(atan(p.y, p.x) * 18.0 + uTime * 0.13), 18.0);
    float longitude = pow(0.5 + 0.5 * sin(atan(p.z, p.x) * 22.0 - uTime * 0.09), 20.0);
    float tracing = max(latitude, longitude) * (0.36 + uActivity * 0.34);
    float alpha = (0.012 + fresnel * 0.16 + tracing * 0.045) * uOpacity;
    vec3 color = mix(uColor * 0.62, uSecondary, clamp(fresnel * 0.68 + tracing * 0.42, 0.0, 1.0));
    gl_FragColor = vec4(color * (0.68 + fresnel * 1.4 + tracing), clamp(alpha, 0.0, 0.34));
  }
`;

export default function MjolnirCoreScene({ audioLevel, quality, reducedMotion, state, suspended }) {
  const runtime = useCoreRuntime(state, audioLevel, reducedMotion, suspended);
  const network = useMemo(() => createSphereNetwork(Math.round(quality.routeCount * 3.35), 32, 7319, 2.02), [quality.routeCount]);
  const surfaceNetwork = useMemo(() => createSurfaceNetwork(Math.round(quality.routeCount * 5.2), 6, 5531, 2.1), [quality.routeCount]);
  const bridgeNetwork = useMemo(() => createSphereNetwork(Math.max(68, Math.round(quality.routeCount * 2.2)), 30, 4403, 1.76), [quality.routeCount]);
  const innerNetwork = useMemo(() => createSphereNetwork(Math.max(72, Math.round(quality.routeCount * 2.45)), 30, 1931, 1.34), [quality.routeCount]);
  const clusterSystems = useMemo(() => CLUSTER_POSITIONS.map((position, index) => ({
    data: createSphereNetwork(Math.max(24, Math.round(quality.routeCount * 0.38)), 22, 8821 + index * 977, 0.4),
    phase: index * 0.91,
    position
  })), [quality.routeCount]);

  return (
    <>
      <fog attach="fog" args={["#02060d", 10.8, 22]} />
      <group position={[0, 0.22, 0]} scale={0.94}>
        <CinematicDrift reducedMotion={reducedMotion} runtime={runtime} />
        <SphericalShell radius={2.22} rotation={[0.16, 0.08, -0.12]} runtime={runtime} speed={0.035} opacity={0.22} />
        <SphericalShell radius={2.13} rotation={[-0.3, 0.42, 0.18]} runtime={runtime} speed={-0.052} opacity={0.18} />
        <SphericalShell radius={2.04} rotation={[0.38, -0.24, 0.3]} runtime={runtime} speed={0.074} opacity={0.14} />
        <NetworkLayer data={surfaceNetwork} opacity={0.68} phaseOffset={1.3} runtime={runtime} speed={0.5} rotationSpeed={-0.018} />
        <NetworkLayer data={network} opacity={0.88} phaseOffset={0.2} runtime={runtime} speed={0.64} rotationSpeed={0.032} />
        <NetworkLayer data={bridgeNetwork} opacity={0.72} phaseOffset={2.4} runtime={runtime} speed={0.88} rotationSpeed={0.024} />
        <NetworkLayer data={innerNetwork} opacity={0.88} phaseOffset={4.1} runtime={runtime} speed={1.22} rotationSpeed={-0.046} />
        <IntelligenceNucleus runtime={runtime} />
        <NeuralClusters clusters={clusterSystems} runtime={runtime} />
        <SphereHaze runtime={runtime} />
        <NodeField count={Math.round(quality.nodeCount * 3.4)} radius={2.08} runtime={runtime} seed={6121} />
        <NodeField count={Math.round(quality.nodeCount * 1.35)} innerRatio={0.78} radius={2.12} runtime={runtime} seed={7717} />
        <InformationPackets count={Math.round(quality.packetCount * 3.2)} routeData={network} runtime={runtime} />
        <OrbitParticles count={Math.max(36, Math.round(quality.nodeCount * 0.58))} runtime={runtime} />
      </group>
      <PrecompileScene />
      <EffectComposer multisampling={quality.multisampling}>
        <AdaptiveBloom runtime={runtime} />
      </EffectComposer>
    </>
  );
}

function useCoreRuntime(state, audioLevel, reducedMotion, suspended) {
  const profile = STATE_PROFILES[state] ?? STATE_PROFILES.idle;
  const targetColor = useMemo(() => new THREE.Color(profile.color), [profile.color]);
  const targetSecondary = useMemo(() => new THREE.Color(profile.secondary), [profile.secondary]);
  const runtime = useRef({
    activity: profile.activity,
    audio: 0,
    color: new THREE.Color(profile.color),
    energy: profile.energy,
    flow: profile.flow,
    secondary: new THREE.Color(profile.secondary),
    speed: profile.speed,
    time: 0
  });

  useFrame((_, delta) => {
    if (suspended) return;
    const dt = Math.min(Math.max(delta, 0), 1 / 30);
    const motionScale = reducedMotion ? 0.12 : 1;
    const current = runtime.current;
    current.activity = THREE.MathUtils.damp(current.activity, profile.activity * motionScale, 2.8, dt);
    current.energy = THREE.MathUtils.damp(current.energy, profile.energy, 2.4, dt);
    current.flow = THREE.MathUtils.damp(current.flow, profile.flow * motionScale, 2.7, dt);
    current.speed = THREE.MathUtils.damp(current.speed, profile.speed * motionScale, 2.1, dt);
    current.audio = THREE.MathUtils.damp(current.audio, audioLevel, 8.5, dt);
    current.color.lerp(targetColor, 1 - Math.exp(-dt * 2.5));
    current.secondary.lerp(targetSecondary, 1 - Math.exp(-dt * 2.5));
    current.time += dt * current.speed;
  });
  return runtime;
}

function SphericalShell({ opacity, radius, rotation, runtime, speed }) {
  const mesh = useRef();
  const material = useRef();
  const uniforms = useMemo(() => ({
    uTime: { value: 0 },
    uActivity: { value: 1 },
    uOpacity: { value: opacity },
    uColor: { value: new THREE.Color("#1687c5") },
    uSecondary: { value: new THREE.Color("#82e9ff") }
  }), [opacity]);

  useFrame(() => {
    if (!mesh.current || !material.current) return;
    const current = runtime.current;
    const breathing = 1 + Math.sin(current.time * 0.11 + radius) * 0.0045;
    mesh.current.scale.setScalar(breathing);
    mesh.current.rotation.x = rotation[0] + current.time * speed * 0.47;
    mesh.current.rotation.y = rotation[1] + current.time * speed;
    mesh.current.rotation.z = rotation[2] - current.time * speed * 0.31;
    material.current.uniforms.uTime.value = current.time;
    material.current.uniforms.uActivity.value = current.activity;
    material.current.uniforms.uColor.value.copy(current.color);
    material.current.uniforms.uSecondary.value.copy(current.secondary);
  });

  return (
    <mesh ref={mesh} renderOrder={1}>
      <sphereGeometry args={[radius, 64, 48]} />
      <shaderMaterial
        blending={THREE.AdditiveBlending}
        depthWrite={false}
        fragmentShader={shellFragmentShader}
        ref={material}
        side={THREE.DoubleSide}
        transparent
        uniforms={uniforms}
        vertexShader={shellVertexShader}
      />
    </mesh>
  );
}

function NetworkLayer({ data, opacity, phaseOffset, rotationSpeed, runtime, speed }) {
  const group = useRef();
  const material = useRef();
  const uniforms = useMemo(() => ({
    uTime: { value: 0 },
    uActivity: { value: 1 },
    uAudio: { value: 0 },
    uOpacity: { value: opacity },
    uSync: { value: 0 },
    uColor: { value: new THREE.Color("#22a8ed") },
    uSecondary: { value: new THREE.Color("#dffaff") }
  }), [opacity]);

  useFrame(() => {
    if (!group.current || !material.current) return;
    const current = runtime.current;
    group.current.rotation.y = current.time * rotationSpeed;
    group.current.rotation.x = Math.sin(current.time * rotationSpeed * 0.7) * 0.12;
    material.current.uniforms.uTime.value = current.time * speed * current.flow;
    material.current.uniforms.uActivity.value = current.activity;
    material.current.uniforms.uAudio.value = current.audio;
    material.current.uniforms.uOpacity.value = opacity * (0.9 + Math.sin(current.time * 0.19 + phaseOffset) * 0.1);
    material.current.uniforms.uSync.value = Math.pow(Math.max(0, Math.sin(current.time * 0.16 + phaseOffset)), 18) * current.energy;
    material.current.uniforms.uColor.value.copy(current.color);
    material.current.uniforms.uSecondary.value.copy(current.secondary);
  });

  return (
    <group ref={group}>
      <lineSegments renderOrder={4}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" array={data.positions} count={data.positions.length / 3} itemSize={3} />
          <bufferAttribute attach="attributes-aProgress" array={data.progress} count={data.progress.length} itemSize={1} />
          <bufferAttribute attach="attributes-aPhase" array={data.phase} count={data.phase.length} itemSize={1} />
          <bufferAttribute attach="attributes-aWeight" array={data.weight} count={data.weight.length} itemSize={1} />
        </bufferGeometry>
        <shaderMaterial
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          fragmentShader={routeFragmentShader}
          ref={material}
          transparent
          uniforms={uniforms}
          vertexShader={routeVertexShader}
        />
      </lineSegments>
    </group>
  );
}

function NodeField({ count, innerRatio = 0.12, radius, runtime, seed }) {
  const material = useRef();
  const data = useMemo(() => createSphereNodes(count, seed, radius, innerRatio), [count, innerRatio, radius, seed]);
  const uniforms = useMemo(() => ({
    uTime: { value: 0 },
    uActivity: { value: 1 },
    uEnergy: { value: 1 },
    uColor: { value: new THREE.Color("#28bafa") },
    uSecondary: { value: new THREE.Color("#e8fcff") }
  }), []);

  useFrame(() => {
    if (!material.current) return;
    const current = runtime.current;
    material.current.uniforms.uTime.value = current.time * current.flow;
    material.current.uniforms.uActivity.value = current.activity;
    material.current.uniforms.uEnergy.value = current.energy;
    material.current.uniforms.uColor.value.copy(current.color);
    material.current.uniforms.uSecondary.value.copy(current.secondary);
  });

  return (
    <points renderOrder={5}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" array={data.positions} count={count} itemSize={3} />
        <bufferAttribute attach="attributes-aPhase" array={data.phase} count={count} itemSize={1} />
        <bufferAttribute attach="attributes-aSize" array={data.size} count={count} itemSize={1} />
      </bufferGeometry>
      <shaderMaterial
        blending={THREE.AdditiveBlending}
        depthWrite={false}
        fragmentShader={pointFragmentShader}
        ref={material}
        transparent
        uniforms={uniforms}
        vertexShader={pointVertexShader}
      />
    </points>
  );
}

function IntelligenceNucleus({ runtime }) {
  const group = useRef();
  const core = useRef();
  const halo = useRef();

  useFrame(() => {
    if (!group.current || !core.current || !halo.current) return;
    const current = runtime.current;
    const transmission = Math.pow(0.5 + 0.5 * Math.sin(current.time * 1.42), 12);
    group.current.scale.setScalar(1 + transmission * 0.16 + current.audio * 0.16);
    core.current.color.copy(current.secondary);
    core.current.opacity = 0.76 + current.energy * 0.18;
    halo.current.color.copy(current.color);
    halo.current.opacity = 0.11 + current.energy * 0.09 + transmission * 0.12;
  });

  return (
    <group ref={group}>
      <mesh renderOrder={8}>
        <sphereGeometry args={[0.072, 20, 16]} />
        <meshBasicMaterial blending={THREE.AdditiveBlending} color="#effeff" depthWrite={false} ref={core} toneMapped={false} transparent />
      </mesh>
      <mesh renderOrder={7}>
        <sphereGeometry args={[0.2, 24, 18]} />
        <meshBasicMaterial blending={THREE.AdditiveBlending} color="#24baff" depthWrite={false} opacity={0.18} ref={halo} toneMapped={false} transparent />
      </mesh>
    </group>
  );
}

function NeuralClusters({ clusters, runtime }) {
  return clusters.map((cluster, index) => (
    <group key={index} position={cluster.position}>
      <NetworkLayer
        data={cluster.data}
        opacity={0.94}
        phaseOffset={cluster.phase}
        rotationSpeed={(index % 2 ? -1 : 1) * (0.038 + index * 0.003)}
        runtime={runtime}
        speed={1.18 + index * 0.035}
      />
      <ClusterPulse phase={cluster.phase} runtime={runtime} />
      <InformationPackets count={14} routeData={cluster.data} runtime={runtime} />
    </group>
  ));
}

function ClusterPulse({ phase, runtime }) {
  const mesh = useRef();
  const material = useRef();

  useFrame(() => {
    if (!mesh.current || !material.current) return;
    const current = runtime.current;
    const synchronization = Math.pow(Math.max(0, Math.sin(current.time * 0.16 + phase)), 18);
    mesh.current.scale.setScalar(0.92 + current.energy * 0.06 + synchronization * 0.18);
    material.current.color.copy(current.secondary);
    material.current.opacity = 0.045 + current.energy * 0.022 + synchronization * 0.11;
  });

  return (
    <mesh ref={mesh} renderOrder={3}>
      <sphereGeometry args={[0.1, 20, 16]} />
      <meshBasicMaterial
        blending={THREE.AdditiveBlending}
        color="#dffaff"
        depthWrite={false}
        opacity={0.06}
        ref={material}
        toneMapped={false}
        transparent
      />
    </mesh>
  );
}

function SphereHaze({ runtime }) {
  const material = useRef();
  const data = useMemo(() => createSphereHaze(68, 2801), []);
  const uniforms = useMemo(() => ({
    uTime: { value: 0 },
    uActivity: { value: 1 },
    uEnergy: { value: 1 },
    uColor: { value: new THREE.Color("#28b9f4") }
  }), []);

  useFrame(() => {
    if (!material.current) return;
    const current = runtime.current;
    material.current.uniforms.uTime.value = current.time;
    material.current.uniforms.uActivity.value = current.activity + current.audio * 0.45;
    material.current.uniforms.uEnergy.value = current.energy + current.audio * 0.38;
    material.current.uniforms.uColor.value.copy(current.color);
  });

  return (
    <points renderOrder={0}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" array={data.positions} count={data.positions.length / 3} itemSize={3} />
        <bufferAttribute attach="attributes-aPhase" array={data.phase} count={data.phase.length} itemSize={1} />
        <bufferAttribute attach="attributes-aSize" array={data.size} count={data.size.length} itemSize={1} />
      </bufferGeometry>
      <shaderMaterial
        blending={THREE.AdditiveBlending}
        depthWrite={false}
        fragmentShader={hazeFragmentShader}
        ref={material}
        transparent
        uniforms={uniforms}
        vertexShader={hazeVertexShader}
      />
    </points>
  );
}

function InformationPackets({ count, routeData, runtime }) {
  const mesh = useRef();
  const descriptors = useMemo(() => createPacketDescriptors(count, routeData.routes, 9917), [count, routeData.routes]);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const point = useMemo(() => new THREE.Vector3(), []);
  const colors = useMemo(() => [new THREE.Color("#20aef3"), new THREE.Color("#61ddff"), new THREE.Color("#e9fdff")], []);

  useLayoutEffect(() => {
    if (!mesh.current) return;
    descriptors.forEach((descriptor, index) => mesh.current.setColorAt(index, colors[descriptor.colorIndex]));
    mesh.current.instanceColor.needsUpdate = true;
  }, [colors, descriptors]);

  useFrame(() => {
    if (!mesh.current) return;
    const current = runtime.current;
    descriptors.forEach((descriptor, index) => {
      const t = (descriptor.offset + current.time * descriptor.route.speed * descriptor.speed * current.flow) % 1;
      descriptor.route.curve.getPoint(t, point);
      const response = 0.7 + Math.pow(0.5 + 0.5 * Math.sin(t * 29 + descriptor.route.phase + current.time), 7) * 0.82;
      dummy.position.copy(point);
      dummy.scale.setScalar(descriptor.scale * response * (0.032 + current.audio * 0.01));
      dummy.rotation.set(0, 0, 0);
      dummy.updateMatrix();
      mesh.current.setMatrixAt(index, dummy.matrix);
    });
    mesh.current.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh args={[null, null, count]} ref={mesh} renderOrder={6}>
      <octahedronGeometry args={[1, 0]} />
      <meshBasicMaterial blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} transparent vertexColors />
    </instancedMesh>
  );
}

function OrbitParticles({ count, runtime }) {
  const mesh = useRef();
  const particles = useMemo(() => createOrbitParticles(count, 4409), [count]);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const point = useMemo(() => new THREE.Vector3(), []);

  useFrame(() => {
    if (!mesh.current) return;
    const time = runtime.current.time;
    particles.forEach((particle, index) => {
      point.copy(particle.base).applyAxisAngle(particle.axis, particle.phase + time * particle.speed);
      dummy.position.copy(point);
      dummy.scale.setScalar(particle.scale);
      dummy.rotation.set(0, 0, 0);
      dummy.updateMatrix();
      mesh.current.setMatrixAt(index, dummy.matrix);
    });
    mesh.current.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh args={[null, null, count]} ref={mesh} renderOrder={5}>
      <sphereGeometry args={[1, 8, 8]} />
      <meshBasicMaterial blending={THREE.AdditiveBlending} color="#88eaff" depthWrite={false} opacity={0.62} toneMapped={false} transparent />
    </instancedMesh>
  );
}

function CinematicDrift({ reducedMotion, runtime }) {
  const { camera } = useThree();
  useFrame((_, delta) => {
    if (reducedMotion) return;
    const dt = Math.min(Math.max(delta, 0), 1 / 30);
    const time = runtime.current.time;
    camera.position.x = THREE.MathUtils.damp(camera.position.x, 0.12 + Math.sin(time * 0.075) * 0.13, 1.25, dt);
    camera.position.y = THREE.MathUtils.damp(camera.position.y, 0.18 + Math.cos(time * 0.061) * 0.07, 1.25, dt);
    camera.position.z = THREE.MathUtils.damp(camera.position.z, 9.35 + Math.sin(time * 0.039) * 0.06, 1.25, dt);
    camera.lookAt(0, 0.04, 0);
  });
  return null;
}

function PrecompileScene() {
  const { gl, scene, camera, invalidate } = useThree();
  useEffect(() => {
    gl.compile(scene, camera);
    invalidate();
  }, [camera, gl, invalidate, scene]);
  return null;
}

function AdaptiveBloom({ runtime }) {
  const bloom = useRef();

  useFrame((_, delta) => {
    if (!bloom.current) return;
    const dt = Math.min(Math.max(delta, 0), 1 / 30);
    const target = THREE.MathUtils.clamp(0.3 + runtime.current.activity * 0.47, 0.34, 0.92);
    bloom.current.intensity = THREE.MathUtils.damp(bloom.current.intensity, target, 2.6, dt);
  });

  return <Bloom intensity={0.7} luminanceSmoothing={0.76} luminanceThreshold={0.48} mipmapBlur radius={0.56} ref={bloom} />;
}
