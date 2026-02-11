"use client";

import { useMemo, useRef } from "react";
import { Points, PointMaterial } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import * as random from "maath/random/dist/maath-random.esm";
import * as THREE from "three";

import type { RuntimeState } from "@/lib/brain-types";

interface NeuralCoreProps {
  state: RuntimeState;
}

const colorByState: Record<RuntimeState, string> = {
  idle: "#3cc9ff",
  thinking: "#ff5470",
  simulating: "#30e0a1",
  error: "#ff9a3c",
};

const speedByState: Record<RuntimeState, number> = {
  idle: 0.5,
  thinking: 2.0,
  simulating: 1.4,
  error: 0.9,
};

export function NeuralCore({ state }: NeuralCoreProps) {
  const groupRef = useRef<THREE.Group | null>(null);
  const cloud = useMemo(
    () => random.inSphere(new Float32Array(7200), { radius: 1.5 }),
    []
  );

  useFrame((ctx, delta) => {
    const group = groupRef.current;
    if (!group) {
      return;
    }

    const speed = speedByState[state];
    group.rotation.x -= delta * 0.22 * speed;
    group.rotation.y -= delta * 0.17 * speed;

    const pulsePower = state === "thinking" ? 0.11 : 0.05;
    const pulseRate = state === "thinking" ? 5.0 : 2.6;
    const scale = 1 + Math.sin(ctx.clock.elapsedTime * pulseRate) * pulsePower;
    group.scale.setScalar(scale);
  });

  return (
    <group ref={groupRef} rotation={[0.2, 0.5, 0]}>
      <Points positions={cloud} stride={3} frustumCulled={false}>
        <PointMaterial
          color={colorByState[state]}
          transparent
          opacity={0.9}
          size={0.007}
          sizeAttenuation
          depthWrite={false}
        />
      </Points>
    </group>
  );
}

