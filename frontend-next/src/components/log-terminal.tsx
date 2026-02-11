"use client";

import { AnimatePresence, motion } from "framer-motion";

import type { BrainEvent } from "@/lib/brain-types";

interface LogTerminalProps {
  events: BrainEvent[];
}

function severityClass(severity: string | undefined): string {
  if (severity === "error") {
    return "text-rose-300";
  }
  if (severity === "warn") {
    return "text-amber-200";
  }
  return "text-cyan-100";
}

export function LogTerminal({ events }: LogTerminalProps) {
  const rows = events.slice(-90).reverse();
  return (
    <section className="panel min-h-[280px] p-0">
      <header className="panel-head px-4 pt-4">
        <span>Cyber Terminal</span>
        <span className="panel-meta">{rows.length} logs</span>
      </header>
      <div className="h-72 overflow-y-auto px-4 pb-4 pt-3 font-mono text-xs lg:h-64">
        <AnimatePresence initial={false}>
          {rows.map((event, idx) => {
            const key = `${event.created_at || "now"}-${event.event_type || "event"}-${idx}`;
            const time = String(event.created_at || "").split("T")[1] || "--:--:--";
            return (
              <motion.div
                key={key}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                className={`mb-1.5 border-l border-cyan-600/40 pl-2 ${severityClass(
                  event.severity
                )}`}
              >
                <span className="text-violet-200/80">[{time}]</span>{" "}
                <span className="text-slate-300">{event.event_type || "event"}</span>{" "}
                <span className="text-slate-100/90">{event.message || ""}</span>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </section>
  );
}

