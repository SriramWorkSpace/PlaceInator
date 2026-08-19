/**
 * Client for the Python sidecar.
 *
 * The shell injects the handshake values on `window` before the app mounts. In
 * `vite dev` there is no shell, so we fall back to env vars — that fallback is
 * the only way to run the UI without a Rust toolchain installed.
 */

import type {
  JobOut,
  ManualJobIn,
  MatchOut,
  ProfileIn,
  ProfileOut,
  ResumeOut,
  SourceFormat,
} from "@/lib/types";

declare global {
  interface Window {
    __PLACEINATOR__?: { port: number; token: string };
  }
}

export class SidecarUnavailableError extends Error {}

interface Connection {
  baseUrl: string;
  token: string;
}

function connection(): Connection {
  const injected = window.__PLACEINATOR__;
  if (injected) {
    return {
      baseUrl: `http://127.0.0.1:${injected.port}`,
      token: injected.token,
    };
  }

  const port = import.meta.env.VITE_SIDECAR_PORT;
  const token = import.meta.env.VITE_SIDECAR_TOKEN;
  if (port && token) {
    return { baseUrl: `http://127.0.0.1:${port}`, token };
  }

  throw new SidecarUnavailableError(
    "No sidecar connection. Run inside the Tauri shell, or start placeinator.main " +
      "manually and set VITE_SIDECAR_PORT / VITE_SIDECAR_TOKEN.",
  );
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { baseUrl, token } = connection();

  // A FormData body (resume upload) must NOT get an explicit Content-Type:
  // the browser sets its own multipart boundary, and overriding it here would
  // send a boundary-less header the server can't parse.
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (!(init.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: { ...headers, ...init.headers },
  });

  if (!response.ok) {
    // FastAPI puts the useful part in `detail`; surface it rather than a bare status.
    let detail = response.statusText;
    try {
      detail = ((await response.json()) as { detail?: string }).detail ?? detail;
    } catch {
      // non-JSON error body; keep the status text
    }
    throw new Error(`${response.status}: ${detail}`);
  }

  return (await response.json()) as T;
}

export interface SidecarStatus {
  status: string;
  version: string;
  data_dir: string;
  database_ok: boolean;
  table_count: number;
}

export const getStatus = () => apiFetch<SidecarStatus>("/api/status");

// -- Profile -----------------------------------------------------------

/** Thrown by getProfile when onboarding has not happened yet (backend 404). */
export class NotOnboardedError extends Error {}

export async function getProfile(): Promise<ProfileOut> {
  try {
    return await apiFetch<ProfileOut>("/api/profile");
  } catch (err) {
    if (err instanceof Error && err.message.startsWith("404:")) {
      throw new NotOnboardedError("profile not onboarded yet");
    }
    throw err;
  }
}

export const putProfile = (data: ProfileIn) =>
  apiFetch<ProfileOut>("/api/profile", { method: "PUT", body: JSON.stringify(data) });

// -- Resumes -------------------------------------------------------------

export const listResumes = () => apiFetch<ResumeOut[]>("/api/resumes");

export function uploadResume(params: {
  label: string;
  sourceFormat: SourceFormat;
  targetRole?: string;
  jobCategory?: string;
  file: File;
}): Promise<ResumeOut> {
  const form = new FormData();
  form.set("label", params.label);
  form.set("source_format", params.sourceFormat);
  if (params.targetRole) form.set("target_role", params.targetRole);
  if (params.jobCategory) form.set("job_category", params.jobCategory);
  form.set("file", params.file);
  return apiFetch<ResumeOut>("/api/resumes", { method: "POST", body: form });
}

// -- Jobs ------------------------------------------------------------------

export const listJobs = () => apiFetch<JobOut[]>("/api/jobs");

export const createManualJob = (data: ManualJobIn) =>
  apiFetch<JobOut>("/api/jobs/manual", { method: "POST", body: JSON.stringify(data) });

// -- Matching --------------------------------------------------------------

export const rankResumesForJob = (jobId: number) =>
  apiFetch<MatchOut[]>(`/api/matching/jobs/${jobId}/rank-resumes`, { method: "POST" });
