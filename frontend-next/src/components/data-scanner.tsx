"use client";

import { motion } from "framer-motion";

interface DataScannerProps {
  fields: string[];
  activeField: string;
}

export function DataScanner({ fields, activeField }: DataScannerProps) {
  return (
    <section className="panel p-4">
      <header className="panel-head">
        <span>Data Ingestion</span>
        <span className="panel-meta">{activeField || "idle"}</span>
      </header>
      <div className="mt-3 grid grid-cols-2 gap-2">
        {fields.map((field) => {
          const active = field.toLowerCase() === activeField.toLowerCase();
          return (
            <motion.div
              key={field}
              animate={{
                borderColor: active ? "rgba(115, 234, 255, 0.95)" : "rgba(82, 92, 128, 0.35)",
                backgroundColor: active
                  ? "rgba(17, 102, 122, 0.34)"
                  : "rgba(10, 12, 24, 0.45)",
              }}
              className="rounded-lg border px-3 py-2 text-xs uppercase tracking-[0.1em]"
            >
              <div className="flex items-center justify-between">
                <span className={active ? "text-cyan-100" : "text-slate-400"}>
                  {field}
                </span>
                {active ? (
                  <motion.span
                    layoutId="scanner-dot"
                    className="size-2 rounded-full bg-cyan-300 shadow-[0_0_10px_rgba(115,234,255,0.95)]"
                  />
                ) : null}
              </div>
            </motion.div>
          );
        })}
      </div>
    </section>
  );
}

