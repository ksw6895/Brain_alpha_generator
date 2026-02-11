"use client";

import { Play, RefreshCcw } from "lucide-react";

import type { ControlActionSpec } from "@/lib/brain-types";

interface CommandConsoleProps {
  actions: ControlActionSpec[];
  selectedAction: string;
  paramsText: string;
  autoStream: boolean;
  jobStatus: string;
  jobHint: string;
  onActionChange: (value: string) => void;
  onParamsChange: (value: string) => void;
  onApplyTemplate: () => void;
  onSubmit: () => void;
  onToggleAutoStream: (value: boolean) => void;
}

export function CommandConsole({
  actions,
  selectedAction,
  paramsText,
  autoStream,
  jobStatus,
  jobHint,
  onActionChange,
  onParamsChange,
  onApplyTemplate,
  onSubmit,
  onToggleAutoStream,
}: CommandConsoleProps) {
  return (
    <section className="panel p-4">
      <header className="panel-head">
        <span>Command Console</span>
        <span className="panel-meta">{jobStatus}</span>
      </header>
      <div className="mt-3 grid gap-2">
        <select
          className="input-base"
          value={selectedAction}
          onChange={(event) => onActionChange(event.target.value)}
        >
          {actions.map((item) => (
            <option key={item.action} value={item.action}>
              {item.action}
            </option>
          ))}
        </select>
        <div className="grid grid-cols-2 gap-2">
          <button className="btn-base" type="button" onClick={onSubmit}>
            <Play size={14} />
            Run
          </button>
          <button className="btn-alt" type="button" onClick={onApplyTemplate}>
            <RefreshCcw size={14} />
            Template
          </button>
        </div>
        <textarea
          className="input-base h-40 resize-y font-mono text-xs"
          value={paramsText}
          onChange={(event) => onParamsChange(event.target.value)}
        />
        <label className="inline-flex items-center gap-2 text-xs text-slate-300">
          <input
            checked={autoStream}
            onChange={(event) => onToggleAutoStream(event.target.checked)}
            type="checkbox"
          />
          Auto stream run_id when completed
        </label>
        <p className="rounded-lg border border-cyan-700/30 bg-cyan-900/15 px-3 py-2 text-xs text-cyan-100/90">
          {jobHint}
        </p>
      </div>
    </section>
  );
}

