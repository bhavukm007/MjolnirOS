import * as THREE from "three";

const TAU = Math.PI * 2;

export function createSphereNetwork(routeCount, segments, seed, radius = 2.04) {
  const random = seededRandom(seed);
  const routes = [];
  const positions = [];
  const progress = [];
  const phase = [];
  const weight = [];
  const junctionCount = Math.max(12, Math.round(routeCount / 7));
  const terminalCount = Math.max(24, Math.round(routeCount * 0.58));
  const nucleus = new THREE.Vector3(0, 0, 0);
  const junctions = Array.from({ length: junctionCount }, (_, index) => {
    if (index === 0) return nucleus.clone();
    const shell = index < Math.ceil(junctionCount * 0.38) ? 0.52 : 0.92;
    return randomPointInSphere(random, radius * shell, index < 4 ? 0.08 : 0.48);
  });
  const terminals = Array.from(
    { length: terminalCount },
    (_, index) => randomPointInSphere(random, radius * (index % 4 === 0 ? 0.995 : 0.97), index % 4 === 0 ? 0.88 : 0.68)
  );

  for (let routeIndex = 0; routeIndex < routeCount; routeIndex += 1) {
    const primaryIndex = routeIndex % junctions.length;
    const primary = junctions[primaryIndex];
    const isNucleusRoute = routeIndex % 15 === 0;
    const reconnects = routeIndex % 4 === 0;
    const secondaryIndex = (primaryIndex + 1 + Math.floor(random() * Math.max(1, junctions.length - 1))) % junctions.length;
    const terminal = terminals[(routeIndex * 7 + Math.floor(random() * terminals.length)) % terminals.length];
    const start = (isNucleusRoute ? nucleus : routeIndex % 3 === 1 ? terminal : primary).clone();
    const end = (isNucleusRoute ? primary : reconnects ? junctions[secondaryIndex] : routeIndex % 3 === 1 ? primary : terminal).clone();
    const midpoint = start.clone().lerp(end, 0.5);
    midpoint.lerp(junctions[(primaryIndex + 3) % junctions.length], 0.08 + random() * 0.12);
    clampToSphere(midpoint, radius * 0.9);

    const tangent = end.clone().sub(start).normalize();
    const bendAxis = new THREE.Vector3(
      (random() - 0.5) * 2,
      (random() - 0.5) * 2,
      (random() - 0.5) * 2
    ).cross(tangent);
    if (bendAxis.lengthSq() < 0.0001) bendAxis.set(-tangent.y, tangent.x, 0.1);
    const bend = bendAxis.normalize().multiplyScalar(0.035 + random() * 0.13);
    const controlA = start.clone().lerp(midpoint, 0.58).add(bend);
    const controlB = midpoint.clone().lerp(end, 0.42).addScaledVector(bend, -0.72);
    clampToSphere(controlA, radius * 0.96);
    clampToSphere(controlB, radius * 0.96);

    const curve = new THREE.CatmullRomCurve3(
      [start, controlA, midpoint, controlB, end],
      false,
      "centripetal",
      0.5
    );
    const samples = curve.getPoints(segments);
    const routePhase = random() * TAU;
    const routeWeight = 0.32 + random() * 0.68;
    routes.push({
      curve,
      phase: routePhase,
      speed: 0.045 + random() * 0.085,
      scale: 0.62 + random() * 0.78
    });

    for (let sample = 0; sample < samples.length - 1; sample += 1) {
      const a = samples[sample];
      const b = samples[sample + 1];
      positions.push(a.x, a.y, a.z, b.x, b.y, b.z);
      progress.push(sample / segments, (sample + 1) / segments);
      phase.push(routePhase, routePhase);
      weight.push(routeWeight, routeWeight);
    }
  }

  return {
    routes,
    positions: new Float32Array(positions),
    progress: new Float32Array(progress),
    phase: new Float32Array(phase),
    weight: new Float32Array(weight)
  };
}

export function createSurfaceNetwork(routeCount, segments, seed, radius = 2.08) {
  const random = seededRandom(seed);
  const nodeCount = Math.max(48, Math.round(routeCount * 0.58));
  const nodes = Array.from({ length: nodeCount }, () => (
    randomUnitVector(random).multiplyScalar(radius * (0.82 + random() * 0.17))
  ));
  const routes = [];
  const positions = [];
  const progress = [];
  const phase = [];
  const weight = [];

  for (let routeIndex = 0; routeIndex < routeCount; routeIndex += 1) {
    const startIndex = routeIndex % nodes.length;
    const start = nodes[startIndex];
    const candidates = nodes
      .map((node, index) => ({ index, distance: index === startIndex ? Infinity : start.distanceToSquared(node) }))
      .sort((a, b) => a.distance - b.distance);
    const neighborBand = Math.min(candidates.length - 1, 2 + routeIndex % 5);
    const end = nodes[candidates[Math.floor(random() * neighborBand)].index];
    const midpoint = start.clone().lerp(end, 0.5).multiplyScalar(0.965 + random() * 0.025);
    const curve = new THREE.CatmullRomCurve3([start.clone(), midpoint, end.clone()], false, "centripetal", 0.5);
    const samples = curve.getPoints(segments);
    const routePhase = random() * TAU;
    const routeWeight = 0.28 + random() * 0.54;
    routes.push({ curve, phase: routePhase, speed: 0.035 + random() * 0.07, scale: 0.48 + random() * 0.62 });

    for (let sample = 0; sample < samples.length - 1; sample += 1) {
      const a = samples[sample];
      const b = samples[sample + 1];
      positions.push(a.x, a.y, a.z, b.x, b.y, b.z);
      progress.push(sample / segments, (sample + 1) / segments);
      phase.push(routePhase, routePhase);
      weight.push(routeWeight, routeWeight);
    }
  }

  return {
    routes,
    positions: new Float32Array(positions),
    progress: new Float32Array(progress),
    phase: new Float32Array(phase),
    weight: new Float32Array(weight)
  };
}

export function createSphereNodes(count, seed, radius = 2.08, innerRatio = 0.12) {
  const random = seededRandom(seed);
  const positions = new Float32Array(count * 3);
  const phase = new Float32Array(count);
  const size = new Float32Array(count);

  for (let index = 0; index < count; index += 1) {
    const point = randomPointInSphere(random, radius, innerRatio);
    positions[index * 3] = point.x;
    positions[index * 3 + 1] = point.y;
    positions[index * 3 + 2] = point.z;
    phase[index] = random() * TAU;
    size[index] = 0.52 + random() * 1.34;
  }
  return { positions, phase, size };
}

export function createSphereHaze(count, seed, radius = 1.58) {
  const random = seededRandom(seed);
  const positions = new Float32Array(count * 3);
  const phase = new Float32Array(count);
  const size = new Float32Array(count);

  for (let index = 0; index < count; index += 1) {
    const point = randomPointInSphere(random, radius, 0);
    positions[index * 3] = point.x;
    positions[index * 3 + 1] = point.y;
    positions[index * 3 + 2] = point.z;
    phase[index] = random() * TAU;
    size[index] = 2.4 + random() * 5;
  }
  return { positions, phase, size };
}

export function createOrbitParticles(count, seed, radius = 2.42) {
  const random = seededRandom(seed);
  return Array.from({ length: count }, () => ({
    axis: randomUnitVector(random),
    base: randomUnitVector(random).multiplyScalar(radius * (0.94 + random() * 0.06)),
    phase: random() * TAU,
    speed: 0.035 + random() * 0.07,
    scale: 0.007 + random() * 0.017
  }));
}

export function createPacketDescriptors(count, routes, seed) {
  const random = seededRandom(seed);
  return Array.from({ length: count }, (_, index) => ({
    route: routes[index % routes.length],
    offset: random(),
    speed: 0.52 + random() * 1.12,
    scale: 0.42 + random() * 0.92,
    colorIndex: random() > 0.78 ? 2 : random() > 0.5 ? 1 : 0
  }));
}

function randomPointInSphere(random, radius, innerRatio) {
  const direction = randomUnitVector(random);
  const innerVolume = innerRatio ** 3;
  const distance = radius * Math.cbrt(innerVolume + random() * (1 - innerVolume));
  return direction.multiplyScalar(distance);
}

function randomUnitVector(random) {
  const y = random() * 2 - 1;
  const angle = random() * TAU;
  const radial = Math.sqrt(Math.max(0, 1 - y * y));
  return new THREE.Vector3(Math.cos(angle) * radial, y, Math.sin(angle) * radial);
}

function clampToSphere(point, radius) {
  if (point.lengthSq() > radius * radius) point.setLength(radius);
  return point;
}

export function seededRandom(seed) {
  let value = Math.abs(Math.floor(seed)) % 2147483647 || 1;
  return () => {
    value = value * 16807 % 2147483647;
    return (value - 1) / 2147483646;
  };
}
