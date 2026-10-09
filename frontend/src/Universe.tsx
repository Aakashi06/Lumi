import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Html, Line } from "@react-three/drei";
import { Color, Group, InstancedMesh, Object3D, Vector3 } from "three";
import { OrbitControls as Controls } from "three-stdlib";
import type { Graph, Node } from "./api";
import { recordMetric } from "./performance";

interface Props {
  graph: Graph;
  selected: string | null;
  onSelect: (id: string) => void;
  focus?: Node;
  onFocus: (node: Node) => void;
  reset: number;
  zoom: { step: number; direction: number };
  landing: boolean;
  light: boolean;
  reducedMotion: boolean;
}
const palette = ["#d9c5a3", "#bec8c6", "#bdc4d0", "#c8b9a9"];
const colorFor = (domain: string) =>
  palette[
    [...domain].reduce((sum, char) => sum + char.charCodeAt(0), 0) %
      palette.length
  ];

function layout(graph: Graph) {
  const started = performance.now();
  const nodes = graph.nodes.slice(0, 220);
  const positions = new Map(
    nodes.map((n) => [n.id, new Vector3(...n.position).multiplyScalar(1.4)]),
  );
  const evidenceEdges = graph.edges.filter(
    (e) =>
      (e.confidence >= 0.75 || e.kind === "cooccurrence") &&
      positions.has(e.source) &&
      positions.has(e.target),
  );
  const unique = new Map<string, (typeof evidenceEdges)[number]>();
  for (const edge of evidenceEdges) {
    const key = `${edge.source}:${edge.target}:${edge.relation}`;
    if (!unique.has(key) || unique.get(key)!.confidence < edge.confidence)
      unique.set(key, edge);
  }
  const edges = [...unique.values()];
  // Deterministic, bounded relaxation. Saved positions are the initial anchors.
  for (let iteration = 0; iteration < 24; iteration++) {
    const forces = new Map(nodes.map((n) => [n.id, new Vector3()]));
    for (let i = 0; i < nodes.length; i++)
      for (let j = i + 1; j < nodes.length; j++) {
        const delta = positions
          .get(nodes[i].id)!
          .clone()
          .sub(positions.get(nodes[j].id)!);
        const distance = Math.max(delta.length(), 0.25);
        delta
          .normalize()
          .multiplyScalar(Math.min(0.12, 0.3 / (distance * distance)));
        forces.get(nodes[i].id)!.add(delta);
        forces.get(nodes[j].id)!.sub(delta);
      }
    for (const edge of edges) {
      const delta = positions
        .get(edge.target)!
        .clone()
        .sub(positions.get(edge.source)!);
      delta.multiplyScalar((delta.length() - 2.8) * 0.004);
      forces.get(edge.source)!.add(delta);
      forces.get(edge.target)!.sub(delta);
    }
    for (const node of nodes)
      positions.get(node.id)!.add(forces.get(node.id)!.clampLength(0, 0.16));
  }
  const center = new Vector3();
  for (const p of positions.values()) center.add(p);
  center.divideScalar(Math.max(nodes.length, 1));
  for (const p of positions.values()) p.sub(center);
  recordMetric("frontend_graph_layout", performance.now() - started);
  return { nodes, positions, edges: edges.slice(0, 600) };
}

function Ticker({ active }: { active: boolean }) {
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(invalidate, 1000 / 30);
    return () => clearInterval(timer);
  }, [active, invalidate]);
  return null;
}

function Camera({
  focus,
  positions,
  reset,
  empty,
  reduced,
  zoom,
  landing,
}: {
  focus?: Node;
  positions: Map<string, Vector3>;
  reset: number;
  empty: boolean;
  reduced: boolean;
  zoom: Props["zoom"];
  landing: boolean;
}) {
  const target = useRef(new Vector3());
  const destination = useRef(new Vector3(0, 3, 18));
  const moving = useRef(true);
  const navigated = useRef(false);
  const previousAction = useRef("");
  const [orbiting, setOrbiting] = useState(true);
  const { camera, invalidate, gl, size } = useThree();
  const controls = useMemo(() => new Controls(camera), [camera]);
  useEffect(() => {
    controls.connect(gl.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minDistance = 3;
    controls.maxDistance = 90;
    const changed = () => {
      // Auto-orbit is driven by the capped ticker, not a self-invalidating loop.
      if (!controls.autoRotate && !document.hidden) invalidate();
    };
    const started = () => {
      moving.current = false;
      navigated.current = true;
      setOrbiting(false);
    };
    controls.addEventListener("change", changed);
    controls.addEventListener("start", started);
    return () => {
      controls.removeEventListener("change", changed);
      controls.removeEventListener("start", started);
      controls.dispose();
    };
  }, [controls, gl, invalidate]);
  useEffect(() => {
    controls.autoRotate = landing && orbiting && !reduced && !focus;
    controls.autoRotateSpeed = 0.24;
  }, [controls, orbiting, reduced, focus, landing]);
  useEffect(() => {
    if (!zoom.step) return;
    moving.current = false;
    navigated.current = true;
    setOrbiting(false);
    const offset = camera.position.clone().sub(controls.target);
    const distance = Math.max(
      controls.minDistance,
      Math.min(
        controls.maxDistance,
        offset.length() * (zoom.direction > 0 ? 0.8 : 1.25),
      ),
    );
    camera.position.copy(controls.target).add(offset.setLength(distance));
    controls.update();
    invalidate();
  }, [zoom.step, zoom.direction, camera, controls, invalidate]);
  const radius = Math.max(5, ...[...positions.values()].map((p) => p.length()));
  useEffect(() => {
    const action = `${focus?.id || "overview"}:${reset}`;
    if (navigated.current && previousAction.current === action) return;
    previousAction.current = action;
    navigated.current = false;
    setOrbiting(true);
    target.current.copy(
      focus
        ? positions.get(focus.id) || new Vector3()
        : new Vector3(empty ? 0 : 0, 0, 0),
    );
    destination.current
      .copy(target.current)
      .add(
        new Vector3(
          focus ? 0 : 2,
          focus ? 1 : 3,
          focus
            ? 6
            : empty
              ? 13
              : (radius * 2.8) / Math.min(1, size.width / size.height),
        ),
      );
    moving.current = true;
    invalidate();
  }, [
    focus?.id,
    reset,
    radius,
    empty,
    positions,
    invalidate,
    size.width,
    size.height,
  ]);
  useFrame((_, delta) => {
    if (!moving.current) {
      controls.update();
      return;
    }
    const smoothing = reduced ? 1 : 1 - Math.exp(-Math.min(delta, 0.1) * 5);
    camera.position.lerp(destination.current, smoothing);
    controls.target.lerp(target.current, smoothing);
    controls.update();
    if (camera.position.distanceTo(destination.current) < 0.015)
      moving.current = false;
    else invalidate();
  });
  return null;
}

function Sculpture({ reduced, light }: { reduced: boolean; light: boolean }) {
  const group = useRef<Group>(null);
  useFrame(({ clock }) => {
    if (group.current && !reduced) {
      group.current.rotation.y = clock.elapsedTime * 0.055;
      group.current.rotation.z = Math.sin(clock.elapsedTime * 0.18) * 0.08;
      group.current.position.y = Math.sin(clock.elapsedTime * 0.45) * 0.13;
    }
  });
  return (
    <group position={[1.5, 0, 0]}>
      <group ref={group}>
        <mesh rotation={[0.6, 0.1, 0.2]}>
          <torusKnotGeometry args={[1.12, 0.31, 180, 20, 2, 3]} />
          <meshPhysicalMaterial
            color={light ? "#c6b08b" : "#b9a178"}
            emissive={light ? "#c6b08b" : "#8d7247"}
            emissiveIntensity={light ? 0.24 : 0.04}
            metalness={light ? 0.48 : 0.82}
            roughness={0.22}
            clearcoat={1}
            clearcoatRoughness={0.2}
          />
        </mesh>
        {[0, 1, 2].map((i) => (
          <group key={i} rotation={[0.5 + i * 0.75, i * 0.9, 0.2 + i * 0.7]}>
            <mesh>
              <torusGeometry args={[2.5 + i * 0.4, 0.012, 6, 160]} />
              <meshBasicMaterial
                color="#c6b493"
                transparent
                opacity={0.25 - i * 0.04}
              />
            </mesh>
            <mesh position={[2.5 + i * 0.4, 0, 0]}>
              <sphereGeometry args={[0.065, 12, 10]} />
              <meshBasicMaterial color="#e3d4b9" />
            </mesh>
          </group>
        ))}
      </group>
    </group>
  );
}

function GraphScene(props: Props & { visible: boolean }) {
  const { graph, selected, onSelect, onFocus, light, reducedMotion, visible } =
    props;
  const signature =
    graph.nodes.map((n) => `${n.id}:${n.position.join(",")}`).join("|") +
    graph.edges
      .map(
        (e) =>
          `${e.source}:${e.target}:${e.relation}:${e.confidence}:${e.kind}`,
      )
      .sort()
      .join("|");
  const mapped = useMemo(() => layout(graph), [signature]);
  const bodies = useRef<InstancedMesh>(null);
  const halos = useRef<InstancedMesh>(null);
  const births = useRef(new Map<string, number>());
  const [hovered, setHovered] = useState<string | null>(null);
  const links = useMemo(
    () =>
      new Set(
        mapped.edges
          .filter(
            (e) =>
              [selected, hovered].includes(e.source) ||
              [selected, hovered].includes(e.target),
          )
          .flatMap((e) => [e.source, e.target]),
      ),
    [selected, hovered, mapped],
  );
  const degrees = useMemo(() => {
    const counts = new Map<string, number>();
    for (const edge of mapped.edges)
      for (const id of [edge.source, edge.target])
        counts.set(id, (counts.get(id) || 0) + 1);
    return counts;
  }, [mapped]);
  const prominent = useMemo(
    () =>
      new Set(
        [...mapped.nodes]
          .sort((a, b) => (degrees.get(b.id) || 0) - (degrees.get(a.id) || 0))
          .slice(0, 7)
          .map((node) => node.id),
      ),
    [mapped, degrees],
  );
  const invalidate = useThree((state) => state.invalidate);
  const dummy = useMemo(() => new Object3D(), []);
  useEffect(() => {
    if (!bodies.current) return;
    mapped.nodes.forEach((node, index) => {
      dummy.position.copy(mapped.positions.get(node.id)!);
      const active = node.id === selected || node.id === hovered;
      dummy.scale.setScalar(
        (0.18 + Math.min(degrees.get(node.id) || 0, 12) * 0.018) *
          (active ? 1.5 : 1),
      );
      dummy.updateMatrix();
      bodies.current!.setMatrixAt(index, dummy.matrix);
      dummy.scale.multiplyScalar(1.85);
      dummy.updateMatrix();
      halos.current?.setMatrixAt(index, dummy.matrix);
      if (!births.current.has(node.id)) births.current.set(node.id, -1);
      const color = new Color(active ? "#f5d6a2" : colorFor(node.domain));
      if ((selected || hovered) && !active && !links.has(node.id))
        color.multiplyScalar(0.3);
      bodies.current!.setColorAt(index, color);
      halos.current?.setColorAt(index, color);
    });
    bodies.current.instanceMatrix.needsUpdate = true;
    bodies.current.computeBoundingSphere();
    if (halos.current) {
      halos.current.instanceMatrix.needsUpdate = true;
      if (halos.current.instanceColor)
        halos.current.instanceColor.needsUpdate = true;
    }
    if (bodies.current.instanceColor)
      bodies.current.instanceColor.needsUpdate = true;
  }, [mapped, selected, hovered, links, degrees, dummy]);
  useFrame(({ clock }) => {
    if (!bodies.current || reducedMotion) return;
    let changed = false;
    mapped.nodes.forEach((node, index) => {
      let birth = births.current.get(node.id) ?? -1;
      if (birth === -1) {
        birth = clock.elapsedTime;
        births.current.set(node.id, birth);
      }
      const age = clock.elapsedTime - birth;
      if (age >= 0.8) return;
      const active = node.id === selected || node.id === hovered;
      dummy.position.copy(mapped.positions.get(node.id)!);
      dummy.scale.setScalar(
        (0.18 + Math.min(degrees.get(node.id) || 0, 12) * 0.018) *
          (active ? 1.5 : 1) *
          (0.15 + 0.85 * Math.min(age / 0.8, 1)),
      );
      dummy.updateMatrix();
      bodies.current!.setMatrixAt(index, dummy.matrix);
      dummy.scale.multiplyScalar(1.85);
      dummy.updateMatrix();
      halos.current?.setMatrixAt(index, dummy.matrix);
      changed = true;
    });
    if (changed) {
      invalidate();
      bodies.current.computeBoundingSphere();
      bodies.current.instanceMatrix.needsUpdate = true;
      if (halos.current) halos.current.instanceMatrix.needsUpdate = true;
    }
  });
  const stars = useMemo(() => {
    const values = new Float32Array(240 * 3);
    for (let i = 0; i < 240; i++) {
      const phi = i * 2.39996;
      const y = 1 - (i / 239) * 2;
      const r = Math.sqrt(1 - y * y);
      values.set(
        [Math.cos(phi) * r * 38, y * 25, Math.sin(phi) * r * 38],
        i * 3,
      );
    }
    return values;
  }, []);
  return (
    <>
      <Ticker active={props.landing && visible && !reducedMotion} />
      <ambientLight intensity={light ? 1.8 : 0.7} />
      <pointLight position={[4, 8, 6]} intensity={180} color="#ffe5b5" />
      <pointLight position={[-5, 2, 4]} intensity={110} color="#dbe9ef" />
      <pointLight position={[0, -4, -4]} intensity={90} color="#c69c73" />
      <Camera
        focus={props.focus}
        positions={mapped.positions}
        reset={props.reset}
        empty={!mapped.nodes.length}
        reduced={reducedMotion}
        zoom={props.zoom}
        landing={props.landing}
      />
      {!light && (
        <points>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" args={[stars, 3]} />
          </bufferGeometry>
          <pointsMaterial
            size={0.045}
            color="#d4c9b4"
            transparent
            opacity={0.35}
            sizeAttenuation
          />
        </points>
      )}
      {!mapped.nodes.length ? (
        props.landing ? (
          <Sculpture reduced={reducedMotion} light={light} />
        ) : null
      ) : (
        <>
          <instancedMesh
            key={mapped.nodes.length}
            ref={bodies}
            args={[undefined, undefined, mapped.nodes.length]}
            onPointerOver={(e) => {
              if (e.instanceId !== undefined) {
                e.stopPropagation();
                setHovered(mapped.nodes[e.instanceId].id);
              }
            }}
            onPointerOut={() => setHovered(null)}
            onClick={(e) => {
              if (e.instanceId !== undefined) {
                e.stopPropagation();
                onSelect(mapped.nodes[e.instanceId].id);
              }
            }}
            onDoubleClick={(e) => {
              if (e.instanceId !== undefined)
                onFocus(mapped.nodes[e.instanceId]);
            }}
          >
            <sphereGeometry args={[1, 16, 12]} />
            <meshStandardMaterial
              metalness={0.55}
              roughness={0.28}
              emissive="#8f7856"
              emissiveIntensity={0.2}
            />
          </instancedMesh>
          <instancedMesh
            key={`halo-${mapped.nodes.length}`}
            ref={halos}
            args={[undefined, undefined, mapped.nodes.length]}
          >
            <sphereGeometry args={[1, 12, 10]} />
            <meshBasicMaterial
              transparent
              opacity={light ? 0.035 : 0.075}
              depthWrite={false}
            />
          </instancedMesh>
          {mapped.edges.map((edge) => {
            const a = mapped.positions.get(edge.source)!,
              b = mapped.positions.get(edge.target)!;
            const active =
              [selected, hovered].includes(edge.source) ||
              [selected, hovered].includes(edge.target);
            const mid = a.clone().lerp(b, 0.5);
            mid.z += Math.min(a.distanceTo(b) * 0.12, 1.2);
            return (
              <group key={edge.id}>
                <Line
                  points={[
                    a,
                    a.clone().lerp(mid, 0.6),
                    mid,
                    b.clone().lerp(mid, 0.6),
                    b,
                  ]}
                  color={active ? "#d8bc8d" : light ? "#958778" : "#7a756c"}
                  dashed={edge.kind === "cooccurrence"}
                  dashSize={0.15}
                  gapSize={0.1}
                  lineWidth={active ? 1.5 : 0.8}
                  transparent
                  opacity={
                    active ? 0.85 : edge.kind === "cooccurrence" ? 0.12 : 0.35
                  }
                />
                {active && selected && (
                  <Html position={mid} center style={{ pointerEvents: "none" }}>
                    <span className="edge-label">
                      {edge.relation.replaceAll("_", " ").toLowerCase()}
                    </span>
                  </Html>
                )}
              </group>
            );
          })}
          {mapped.nodes
            .filter(
              (n, i) =>
                n.id === selected ||
                n.id === hovered ||
                (mapped.nodes.length < 16 && i < 8) ||
                prominent.has(n.id) ||
                links.has(n.id),
            )
            .map((node) => (
              <Html
                key={node.id}
                position={mapped.positions.get(node.id)!}
                center
                style={{ pointerEvents: "none" }}
              >
                <span
                  className={`node-label ${node.id === selected || node.id === hovered ? "active" : ""}`}
                >
                  {node.name}
                </span>
              </Html>
            ))}
        </>
      )}
    </>
  );
}

export default function Universe(props: Props) {
  const [visible, setVisible] = useState(!document.hidden);
  useEffect(() => {
    const changed = () => setVisible(!document.hidden);
    document.addEventListener("visibilitychange", changed);
    return () => document.removeEventListener("visibilitychange", changed);
  }, []);
  return (
    <Canvas
      camera={{ position: [2, 3, 18], fov: 44 }}
      dpr={[1, 1.4]}
      frameloop="demand"
      gl={{ antialias: true, alpha: true, powerPreference: "low-power" }}
    >
      <GraphScene {...props} visible={visible} />
    </Canvas>
  );
}
