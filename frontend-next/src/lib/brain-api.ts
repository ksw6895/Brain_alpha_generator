import type {
  ControlActionsResponse,
  ControlJob,
} from "@/lib/brain-types";

const apiBase = (
  process.env.NEXT_PUBLIC_BRAIN_API_BASE || "http://127.0.0.1:8765"
).replace(/\/+$/, "");

function buildUrl(path: string): string {
  if (/^https?:\/\//.test(path)) {
    return path;
  }
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${apiBase}${normalized}`;
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(buildUrl(path), {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail =
      typeof payload?.detail === "string"
        ? payload.detail
        : `status=${response.status}`;
    throw new Error(detail);
  }
  return payload as T;
}

export function getApiBase(): string {
  return apiBase;
}

export function getWsBase(): string {
  const override = process.env.NEXT_PUBLIC_BRAIN_WS_BASE;
  if (override && override.trim()) {
    return override.replace(/\/+$/, "");
  }
  return apiBase.replace(/^http/i, "ws");
}

export async function getControlActions(): Promise<ControlActionsResponse> {
  return fetchJson<ControlActionsResponse>("/api/control/actions");
}

export async function enqueueControlJob(
  action: string,
  params: Record<string, unknown>
): Promise<ControlJob> {
  return fetchJson<ControlJob>("/api/control/jobs", {
    method: "POST",
    body: JSON.stringify({ action, params }),
  });
}

export async function getControlJob(jobId: string): Promise<ControlJob> {
  return fetchJson<ControlJob>(`/api/control/jobs/${encodeURIComponent(jobId)}`);
}

