"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Stars } from "@react-three/drei";
import { motion } from "framer-motion";
import { Activity, RadioTower, Waypoints } from "lucide-react";

import {
  enqueueControlJob,
  getControlActions,
  getControlJob,
  getWsBase,
} from "@/lib/brain-api";
import type {
  BacktestPoint,
  BrainEvent,
  ControlActionSpec,
  ReactorPayload,
  RuntimeState,
} from "@/lib/brain-types";
import { BacktestChart } from "@/components/backtest-chart";
import { CommandConsole } from "@/components/command-console";
import { DataScanner } from "@/components/data-scanner";
import { GenomeMap } from "@/components/genome-map";
import { LogTerminal } from "@/components/log-terminal";
import { NeuralCore } from "@/components/neural-core";

const scannerFields = [
  "Open",
  "High",
  "Low",
  "Close",
  "Volume",
  "VWAP",
  "Returns",
  "Momentum",
  "Sentiment",
];

const fieldHintByEvent: Record<string, string> = {
  "retrieval.pack_built": "Close",
  "validation.retry_started": "Returns",
  "simulation.started": "Volume",
  "simulation.progress": "VWAP",
  "evaluation.completed": "Momentum",
};

function toRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function parseFormula(payload: Record<string, unknown>): string | null {
  const direct = payload.regular;
  if (typeof direct === "string" && direct.trim()) {
    return `$ alpha = ${direct.trim()}`;
  }
  const nestedCandidate = toRecord(payload.candidate);
  const nestedRegular = nestedCandidate.regular;
  if (typeof nestedRegular === "string" && nestedRegular.trim()) {
    return `$ alpha = ${nestedRegular.trim()}`;
  }
  return null;
}

export default function Home() {
  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<number | null>(null);
  const backtestStepRef = useRef(0);

  const [runIdInput, setRunIdInput] = useState("");
  const [activeRunId, setActiveRunId] = useState("");
  const [connectionStatus, setConnectionStatus] = useState("idle");
  const [runtimeState, setRuntimeState] = useState<RuntimeState>("idle");
  const [activeField, setActiveField] = useState("Close");
  const [formula, setFormula] = useState(
    "$ alpha = ts_decay_linear(correlation(close, volume, 10), 5)"
  );

  const [actions, setActions] = useState<ControlActionSpec[]>([]);
  const [selectedAction, setSelectedAction] = useState("");
  const [paramsText, setParamsText] = useState("{}");
  const [autoStreamRun, setAutoStreamRun] = useState(true);
  const [jobStatus, setJobStatus] = useState("job: idle");
  const [jobHint, setJobHint] = useState("Load action templates, adjust params, run.");

  const [events, setEvents] = useState<BrainEvent[]>([]);
  const [backtestSeries, setBacktestSeries] = useState<BacktestPoint[]>([]);
  const [latestSharpe, setLatestSharpe] = useState<number | null>(null);
  const [reactor, setReactor] = useState<ReactorPayload>({});

  const pressure = useMemo(() => {
    const v = reactor.gauges?.pressure;
    return Number.isFinite(v) ? Number(v) : 0;
  }, [reactor]);

  const appendEvent = useCallback((event: BrainEvent) => {
    setEvents((prev) => [...prev.slice(-260), event]);
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const closeSocket = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const applyTemplate = useCallback(
    (action: string) => {
      const spec = actions.find((row) => row.action === action);
      const payload = spec?.template ?? {};
      setParamsText(JSON.stringify(payload, null, 2));
    },
    [actions]
  );

  const ingestEvent = useCallback(
    (event: BrainEvent) => {
      appendEvent(event);
      const eventType = String(event.event_type || "");
      const payload = toRecord(event.payload);
      const incomingRun = String(event.run_id || "").trim();
      if (incomingRun) {
        setActiveRunId(incomingRun);
      }

      if (eventType === "reactor.status") {
        setReactor(toRecord(payload) as ReactorPayload);
      }

      const formulaCandidate = parseFormula(payload);
      if (formulaCandidate) {
        setFormula(formulaCandidate);
      }

      const usedFields = payload.used_fields;
      if (Array.isArray(usedFields) && usedFields.length > 0) {
        const first = usedFields.find((item) => typeof item === "string");
        if (typeof first === "string" && first.trim()) {
          setActiveField(first.trim());
        }
      } else {
        const hint = fieldHintByEvent[eventType];
        if (hint) {
          setActiveField(hint);
        }
      }

      if (eventType === "agent.idea_started" || eventType === "agent.alpha_started") {
        setRuntimeState("thinking");
      } else if (
        eventType === "simulation.started" ||
        eventType === "simulation.progress"
      ) {
        setRuntimeState("simulating");
      } else if (
        eventType === "control.job_failed" ||
        eventType === "budget.blocked" ||
        eventType === "validation.retry_failed"
      ) {
        setRuntimeState("error");
      } else if (eventType === "run.summary" || eventType === "control.job_completed") {
        setRuntimeState("idle");
      }

      if (eventType === "simulation.completed" || eventType === "simulation_completed") {
        const metrics = toRecord(payload.metrics);
        const sharpe = toNumber(metrics.sharpe);
        const fitness = toNumber(metrics.fitness);
        if (sharpe !== null) {
          setLatestSharpe(sharpe);
        }
        const composite = (sharpe ?? 0) * 0.65 + (fitness ?? 0) * 0.35;
        setBacktestSeries((prev) => {
          const last = prev.length > 0 ? prev[prev.length - 1].score : 0;
          backtestStepRef.current += 1;
          const next: BacktestPoint = {
            step: backtestStepRef.current,
            score: Number((last + composite).toFixed(4)),
            sharpe: Number((sharpe ?? 0).toFixed(4)),
          };
          return [...prev.slice(-160), next];
        });
      }
    },
    [appendEvent]
  );

  const connect = useCallback(
    (targetRunId: string) => {
      closeSocket();
      const params = new URLSearchParams({
        replay: "90",
        include_reactor: "1",
        reactor_interval_sec: "1.0",
      });
      if (targetRunId.trim()) {
        params.set("run_id", targetRunId.trim());
      }

      const ws = new WebSocket(`${getWsBase()}/ws/live?${params.toString()}`);
      wsRef.current = ws;
      setConnectionStatus("connecting");

      ws.onopen = () => {
        setConnectionStatus("connected");
      };
      ws.onerror = () => {
        setConnectionStatus("error");
      };
      ws.onclose = () => {
        setConnectionStatus("closed");
      };
      ws.onmessage = (msg) => {
        try {
          ingestEvent(JSON.parse(msg.data) as BrainEvent);
        } catch {
          appendEvent({
            event_type: "ui.parse_error",
            severity: "warn",
            message: "Malformed websocket frame received",
            created_at: new Date().toISOString(),
          });
        }
      };
    },
    [appendEvent, closeSocket, ingestEvent]
  );

  const startJobPolling = useCallback(
    (jobId: string) => {
      stopPolling();
      const poll = async () => {
        try {
          const job = await getControlJob(jobId);
          setJobStatus(`job: ${job.status} ${jobId.slice(0, 8)}`);

          if (job.status === "completed" || job.status === "failed") {
            stopPolling();
            if (job.status === "completed") {
              const runId =
                String(job.result?.run_id || job.run_id || "").trim();
              setJobHint(`completed: ${job.action}`);
              if (runId && autoStreamRun) {
                setRunIdInput(runId);
                connect(runId);
              }
            } else {
              setJobHint(
                String(job.stderr_tail || "job failed").slice(-180) || "job failed"
              );
            }
          }
        } catch (error) {
          setJobStatus("job: poll error");
          setJobHint(String(error));
          stopPolling();
        }
      };

      void poll();
      pollRef.current = window.setInterval(() => {
        void poll();
      }, 1400);
    },
    [autoStreamRun, connect, stopPolling]
  );

  const submitCommand = useCallback(async () => {
    if (!selectedAction) {
      setJobHint("Select an action first.");
      return;
    }
    let params: Record<string, unknown>;
    try {
      const parsed = JSON.parse(paramsText);
      params = toRecord(parsed);
    } catch (error) {
      setJobStatus("job: invalid params");
      setJobHint(`JSON parse error: ${String(error)}`);
      return;
    }

    setJobStatus("job: submitting");
    try {
      const job = await enqueueControlJob(selectedAction, params);
      setJobStatus(`job: queued ${job.job_id.slice(0, 8)}`);
      setJobHint(`action=${selectedAction}`);
      startJobPolling(job.job_id);
    } catch (error) {
      setJobStatus("job: submit failed");
      setJobHint(String(error));
    }
  }, [paramsText, selectedAction, startJobPolling]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const payload = await getControlActions();
        if (!active) {
          return;
        }
        const rows = Array.isArray(payload.actions) ? payload.actions : [];
        setActions(rows);
        if (rows.length === 0) {
          return;
        }
        const defaultAction =
          rows.find((item) => item.action === "run-quick-validation-loop")?.action ||
          rows[0].action;
        setSelectedAction(defaultAction);
        const selected = rows.find((item) => item.action === defaultAction);
        setParamsText(JSON.stringify(selected?.template ?? {}, null, 2));
      } catch (error) {
        setJobHint(`action load failed: ${String(error)}`);
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const runFromQuery = new URLSearchParams(window.location.search).get("run_id") || "";
    setRunIdInput(runFromQuery);
    connect(runFromQuery);
    return () => {
      stopPolling();
      closeSocket();
    };
  }, [closeSocket, connect, stopPolling]);

  const runtimeLabel = runtimeState.toUpperCase();

  return (
    <main className="relative min-h-screen overflow-hidden px-4 py-5 text-slate-100 sm:px-6">
      <div className="bg-grid pointer-events-none absolute inset-0 opacity-55" />
      <div className="pointer-events-none absolute -left-20 top-10 h-60 w-60 rounded-full bg-cyan-600/20 blur-3xl" />
      <div className="pointer-events-none absolute bottom-0 right-0 h-72 w-72 rounded-full bg-fuchsia-500/20 blur-3xl" />

      <header className="mb-4 flex flex-col gap-3 rounded-2xl border border-slate-700/60 bg-slate-900/65 p-4 backdrop-blur sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-cyan-200/80">
            Neural Reactor
          </p>
          <h1 className="font-[var(--font-orbitron)] text-3xl font-semibold tracking-tight text-slate-50">
            Brain Alpha Generator Control Deck
          </h1>
          <p className="text-sm text-slate-300/90">
            Next.js + React Three Fiber + FastAPI WebSocket runtime console
          </p>
        </div>
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            connect(runIdInput.trim());
          }}
        >
          <input
            className="input-base min-w-56"
            value={runIdInput}
            onChange={(event) => setRunIdInput(event.target.value)}
            placeholder="run_id (optional)"
          />
          <button className="btn-base" type="submit">
            <RadioTower size={14} />
            Stream
          </button>
        </form>
      </header>

      <section className="grid gap-4 lg:grid-cols-12">
        <aside className="grid gap-4 lg:col-span-3">
          <article className="panel p-4">
            <header className="panel-head">
              <span>System Status</span>
              <span className="panel-meta">{connectionStatus}</span>
            </header>
            <div className="mt-3 grid gap-3 text-sm">
              <div className="rounded-xl border border-cyan-800/45 bg-cyan-900/20 p-3">
                <p className="text-xs uppercase tracking-[0.16em] text-cyan-200/80">
                  Runtime
                </p>
                <p className="mt-1 text-2xl font-semibold text-cyan-100">
                  {runtimeLabel}
                </p>
              </div>
              <div className="rounded-xl border border-fuchsia-800/50 bg-fuchsia-900/20 p-3">
                <p className="text-xs uppercase tracking-[0.16em] text-fuchsia-200/80">
                  Active run_id
                </p>
                <p className="mt-1 truncate font-mono text-sm text-fuchsia-100/90">
                  {activeRunId || "-"}
                </p>
              </div>
              <div className="rounded-xl border border-emerald-800/45 bg-emerald-900/20 p-3">
                <p className="text-xs uppercase tracking-[0.16em] text-emerald-200/80">
                  Pressure
                </p>
                <p className="mt-1 text-xl font-semibold text-emerald-100">
                  {(pressure * 100).toFixed(1)}%
                </p>
              </div>
            </div>
          </article>
          <DataScanner fields={scannerFields} activeField={activeField} />
          <GenomeMap fields={scannerFields} activeField={activeField} />
        </aside>

        <section className="grid gap-4 lg:col-span-6">
          <article className="panel relative min-h-[520px] overflow-hidden p-0">
            <motion.div
              initial={{ opacity: 0.2 }}
              animate={{ opacity: runtimeState === "thinking" ? 0.85 : 0.35 }}
              className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(128,49,255,0.25)_0%,rgba(4,8,18,0)_70%)]"
            />
            <div className="absolute left-4 top-4 z-20 rounded-lg border border-cyan-700/40 bg-slate-950/65 p-3 backdrop-blur">
              <p className="text-xs uppercase tracking-[0.2em] text-cyan-200/80">
                Reactor Core
              </p>
              <p className="mt-1 text-sm text-slate-100">{formula}</p>
            </div>
            <div className="absolute right-4 top-4 z-20 flex gap-2">
              <span className="chip">
                <Activity size={13} />
                {runtimeState}
              </span>
              <span className="chip">
                <Waypoints size={13} />
                {activeField}
              </span>
            </div>
            <Canvas camera={{ position: [0, 0, 5.1], fov: 45 }}>
              <Suspense fallback={null}>
                <ambientLight intensity={0.45} />
                <pointLight position={[1.8, 1.4, 2.2]} intensity={1.2} color="#80ecff" />
                <pointLight position={[-2, -1.3, -1]} intensity={0.9} color="#ff6f91" />
                <Stars
                  radius={40}
                  depth={40}
                  count={1200}
                  factor={2.4}
                  saturation={0}
                  fade
                  speed={0.35}
                />
                <NeuralCore state={runtimeState} />
              </Suspense>
            </Canvas>
          </article>
        </section>

        <aside className="grid gap-4 lg:col-span-3">
          <CommandConsole
            actions={actions}
            selectedAction={selectedAction}
            paramsText={paramsText}
            autoStream={autoStreamRun}
            jobStatus={jobStatus}
            jobHint={jobHint}
            onActionChange={(value) => {
              setSelectedAction(value);
              const spec = actions.find((row) => row.action === value);
              setParamsText(JSON.stringify(spec?.template ?? {}, null, 2));
            }}
            onParamsChange={setParamsText}
            onApplyTemplate={() => applyTemplate(selectedAction)}
            onSubmit={() => {
              void submitCommand();
            }}
            onToggleAutoStream={setAutoStreamRun}
          />
          <BacktestChart points={backtestSeries} latestSharpe={latestSharpe} />
        </aside>

        <section className="lg:col-span-12">
          <LogTerminal events={events} />
        </section>
      </section>
    </main>
  );
}
