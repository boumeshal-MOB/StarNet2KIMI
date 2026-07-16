import type { AuditEvent, Bootstrap, ProcessingSummary, RunDetail, RunSummary, VersionPayload } from "./types";

const BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    let detail = `${response.status}`;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      /* keep status */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return response.json() as Promise<T>;
}

export const api = {
  bootstrap: () => request<Bootstrap>("/bootstrap"),
  audit: (processingId?: number) => request<AuditEvent[]>(`/audit${processingId ? `?processing_id=${processingId}` : ""}`),

  processings: () => request<ProcessingSummary[]>("/processings"),
  processing: (id: number) => request<ProcessingSummary>(`/processings/${id}`),
  createProcessing: (body: { name: string; description: string; kind: string; template: string; state: string; payload: VersionPayload }) =>
    request<ProcessingSummary>("/processings", { method: "POST", body: JSON.stringify(body) }),
  updateProcessing: (id: number, body: Record<string, unknown>) =>
    request<ProcessingSummary>(`/processings/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

  createDraft: (processingId: number, fromVersionId: number, payload?: VersionPayload) =>
    request<{ id: number; number: number }>(`/processings/${processingId}/versions`, {
      method: "POST",
      body: JSON.stringify(payload ? { from_version_id: fromVersionId, payload } : { from_version_id: fromVersionId }),
    }),
  activateVersion: (processingId: number, versionId: number, validFrom?: string) =>
    request(`/processings/${processingId}/versions/${versionId}/activate`, { method: "POST", body: JSON.stringify(validFrom ? { valid_from: validFrom } : {}) }),
  archiveVersion: (processingId: number, versionId: number) =>
    request(`/processings/${processingId}/versions/${versionId}/archive`, { method: "POST", body: JSON.stringify({}) }),
  compareVersions: (processingId: number, a: number, b: number) =>
    request<{ a: number; b: number; diff: { path: string; from: unknown; to: unknown }[] }>(`/processings/${processingId}/compare?a=${a}&b=${b}`),

  run: (processingId: number, slot?: string) =>
    request<RunDetail>(`/processings/${processingId}/run`, { method: "POST", body: JSON.stringify(slot ? { slot } : {}) }),
  reprocess: (processingId: number, fromSlot: string, toSlot: string) =>
    request<{ slots: number; results: { id: number; slot: string; status: string; chi_square_status: string }[] }>(
      `/processings/${processingId}/reprocess`,
      { method: "POST", body: JSON.stringify({ from_slot: fromSlot, to_slot: toSlot }) },
    ),
  runs: (processingId: number) => request<RunSummary[]>(`/processings/${processingId}/runs`),
  runDetail: (runId: number) => request<RunDetail>(`/runs/${runId}`),
  outputs: (processingId: number, component: string) =>
    request<{ component: string; series: Record<string, { slot: string; value: number; run_id: number }[]> }>(
      `/processings/${processingId}/outputs?component=${component}`,
    ),

  analysisTrial: (body: { processing_id: number; slot: string; version_id?: number; overrides: Record<string, unknown> }) =>
    request<RunDetail>("/analysis/trial", { method: "POST", body: JSON.stringify(body) }),
  analysisSaveDraft: (body: { processing_id: number; base_version_id: number; payload: VersionPayload; note: string }) =>
    request<{ id: number; number: number }>("/analysis/save-draft", { method: "POST", body: JSON.stringify(body) }),

  demoState: () => request<{ late_data: { delivered: boolean; cycle: string; count: number } | null; stats: Record<string, number> }>("/demo/state"),
  demoReset: () => request("/demo/reset", { method: "POST", body: JSON.stringify({}) }),
  demoDeliverLate: () =>
    request<{ delivered: boolean; cycle?: string; catch_up: { slot: string; status: string }[] }>("/demo/deliver-late", {
      method: "POST",
      body: JSON.stringify({}),
    }),
};
