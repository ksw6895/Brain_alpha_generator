"use client";

import { useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  type Edge,
  type Node,
} from "reactflow";
import "reactflow/dist/style.css";

interface GenomeMapProps {
  fields: string[];
  activeField: string;
}

function buildGraph(fields: string[], activeField: string): {
  nodes: Node[];
  edges: Edge[];
} {
  const centerId = "core";
  const center: Node = {
    id: centerId,
    position: { x: 250, y: 170 },
    data: { label: "Alpha Target" },
    style: {
      borderRadius: 999,
      border: "1px solid rgba(163, 98, 255, 0.65)",
      width: 120,
      height: 120,
      display: "grid",
      placeItems: "center",
      color: "#f8edff",
      background:
        "radial-gradient(circle at 35% 35%, rgba(165,114,255,0.55), rgba(39,14,76,0.8))",
      boxShadow: "0 0 30px rgba(120, 52, 255, 0.35)",
      fontSize: 11,
      textAlign: "center",
      letterSpacing: "0.08em",
      textTransform: "uppercase",
      fontWeight: 600,
    },
    draggable: false,
    selectable: false,
  };

  const nodes: Node[] = [center];
  const edges: Edge[] = [];
  const radius = 165;

  fields.forEach((field, index) => {
    const theta = (Math.PI * 2 * index) / Math.max(fields.length, 1);
    const active = field.toLowerCase() === activeField.toLowerCase();
    const id = `field-${field.toLowerCase()}`;
    nodes.push({
      id,
      position: {
        x: center.position.x + Math.cos(theta) * radius,
        y: center.position.y + Math.sin(theta) * radius,
      },
      data: { label: field },
      style: {
        borderRadius: 14,
        border: active
          ? "1px solid rgba(71, 225, 182, 0.95)"
          : "1px solid rgba(78, 96, 126, 0.75)",
        background: active
          ? "linear-gradient(155deg, rgba(46, 201, 163, 0.42), rgba(20, 58, 69, 0.55))"
          : "linear-gradient(155deg, rgba(26, 31, 51, 0.8), rgba(18, 22, 37, 0.85))",
        color: active ? "#e8fff7" : "#d5d9f2",
        boxShadow: active ? "0 0 22px rgba(59, 223, 177, 0.32)" : "none",
        padding: "7px 10px",
        minWidth: 92,
        fontSize: 11,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
      },
      draggable: false,
      selectable: false,
    });

    edges.push({
      id: `edge-${id}`,
      source: centerId,
      target: id,
      animated: active,
      style: {
        stroke: active ? "rgba(59, 223, 177, 0.95)" : "rgba(92, 117, 157, 0.45)",
        strokeWidth: active ? 2.5 : 1.35,
      },
    });
  });

  return { nodes, edges };
}

export function GenomeMap({ fields, activeField }: GenomeMapProps) {
  const graph = useMemo(() => buildGraph(fields, activeField), [fields, activeField]);

  return (
    <section className="panel h-[300px] p-0 lg:h-full">
      <header className="panel-head px-4 pt-4">
        <span>Alpha Genome Map</span>
        <span className="panel-meta">react-flow</span>
      </header>
      <div className="h-[250px] lg:h-[calc(100%-42px)]">
        <ReactFlow
          nodes={graph.nodes}
          edges={graph.edges}
          fitView
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          panOnDrag={false}
          zoomOnPinch={false}
          zoomOnScroll={false}
          zoomOnDoubleClick={false}
          proOptions={{ hideAttribution: true }}
          minZoom={0.7}
          maxZoom={1}
        >
          <Background gap={24} size={1} color="rgba(110, 130, 168, 0.13)" />
          <Controls showInteractive={false} position="bottom-right" />
        </ReactFlow>
      </div>
    </section>
  );
}
