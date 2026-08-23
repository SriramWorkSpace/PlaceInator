/**
 * Client for the Python sidecar.
 *
 * The shell injects the handshake values on `window` before the app mounts. In
 * `vite dev` there is no shell, so we fall back to env vars — that fallback is
 * the only way to run the UI without a Rust toolchain installed.
 */

import type {
  AtsFeedIn,
  AtsFeedOut,
  DraftIn,
  ExtractedJobFields,
  ExtractedProfileFields,
  JdSourceFormat,
  JobOut,
  JobRanking,
  JobSearchIn,
  JobSearchOut,
  ManualJobIn,
  MatchOut,
  OutreachDraftOut,
  OutreachTargetOut,
  PlacementConnectionStatus,
  PlacementRecordOut,
  PlacementTimeline,
  ProfileIn,
  ProfileOut,
  ResumeOut,
  SkillGapOut,
  SourceFormat,
  TailorIn,
  TailorOut,
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

  // 204 No Content (and any other genuinely empty body) has nothing to
  // parse -- response.json() throws a SyntaxError on an empty string.
  // Placement's sync/disconnect/reject endpoints are this project's first
  // 204 responses; every prior endpoint always returned a JSON body, so
  // this never came up before.
  if (response.status === 204) {
    return undefined as T;
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
  isPrimary?: boolean;
  file: File;
}): Promise<ResumeOut> {
  const form = new FormData();
  form.set("label", params.label);
  form.set("source_format", params.sourceFormat);
  if (params.targetRole) form.set("target_role", params.targetRole);
  if (params.jobCategory) form.set("job_category", params.jobCategory);
  form.set("is_primary", params.isPrimary ? "true" : "false");
  form.set("file", params.file);
  return apiFetch<ResumeOut>("/api/resumes", { method: "POST", body: form });
}

/** Parses an uploaded resume for onboarding autofill only -- writes nothing,
 * and works before a profile exists. */
export function extractProfileFromResume(params: {
  sourceFormat: SourceFormat;
  file: File;
}): Promise<ExtractedProfileFields> {
  const form = new FormData();
  form.set("source_format", params.sourceFormat);
  form.set("file", params.file);
  return apiFetch<ExtractedProfileFields>("/api/resumes/extract", { method: "POST", body: form });
}

export const setPrimaryResume = (resumeId: number) =>
  apiFetch<ResumeOut>(`/api/resumes/${resumeId}/primary`, { method: "PATCH" });

// -- Jobs ------------------------------------------------------------------

export const listJobs = () => apiFetch<JobOut[]>("/api/jobs");

/** Keyword/location search against indeed/linkedin/naukri (ADR 0003).
 * `blocked_reason` set with an empty `jobs` list is an expected, common
 * outcome for linkedin/naukri, not an error -- the caller should offer
 * manual paste, not surface a failure. */
export const searchJobs = (data: JobSearchIn) =>
  apiFetch<JobSearchOut>("/api/jobs/search", { method: "POST", body: JSON.stringify(data) });

/** Pulls every open posting from a company's public ATS board (Greenhouse,
 * Lever, Ashby). Unlike `searchJobs` this is company-scoped, not keyword
 * search -- each entry is "platform:company-slug". These are official public
 * APIs, so unlike the scraped boards they reliably return full descriptions. */
export const syncAtsFeed = (data: AtsFeedIn) =>
  apiFetch<AtsFeedOut>("/api/jobs/ats-feed", { method: "POST", body: JSON.stringify(data) });

/** Best-first, hard-filtered jobs kept (never hidden) but sorted last with
 * their reason attached. Requires onboarding -- ranking is meaningless
 * without Preferences to rank against. */
export async function listRankedJobs(): Promise<JobRanking[]> {
  try {
    return await apiFetch<JobRanking[]>("/api/jobs/ranked");
  } catch (err) {
    if (err instanceof Error && err.message.startsWith("412:")) {
      throw new NotOnboardedError("profile not onboarded yet");
    }
    throw err;
  }
}

/** Jobs worth interrupting the user for: passes hard filters, scores above
 * the match threshold, and hasn't been marked seen yet. */
export async function listJobNotifications(): Promise<JobRanking[]> {
  try {
    return await apiFetch<JobRanking[]>("/api/jobs/notifications");
  } catch (err) {
    if (err instanceof Error && err.message.startsWith("412:")) {
      throw new NotOnboardedError("profile not onboarded yet");
    }
    throw err;
  }
}

export const markNotificationSeen = (jobId: number) =>
  apiFetch<JobOut>(`/api/jobs/${jobId}/notifications/seen`, { method: "POST" });

export const createManualJob = (data: ManualJobIn) =>
  apiFetch<JobOut>("/api/jobs/manual", { method: "POST", body: JSON.stringify(data) });

/** Parses an uploaded JD (PDF/DOCX) for the manual-add form -- writes
 * nothing. */
export function extractJobFromFile(params: {
  sourceFormat: JdSourceFormat;
  file: File;
}): Promise<ExtractedJobFields> {
  const form = new FormData();
  form.set("source_format", params.sourceFormat);
  form.set("file", params.file);
  return apiFetch<ExtractedJobFields>("/api/jobs/extract", { method: "POST", body: form });
}

// -- Matching --------------------------------------------------------------

export const rankResumesForJob = (jobId: number) =>
  apiFetch<MatchOut[]>(`/api/matching/jobs/${jobId}/rank-resumes`, { method: "POST" });

// -- Latex -------------------------------------------------------------------

/** Reorders/selects/emphasizes an existing library resume for a job -- never
 * rewrites prose (ADR 0002). Recomputes and overwrites on every call, so
 * toggling `excluded_bullet_ids` and calling again is the normal flow. */
export const tailorResume = (data: TailorIn) =>
  apiFetch<TailorOut>("/api/latex/tailor", { method: "POST", body: JSON.stringify(data) });

// -- Placement automation (spec §7) -----------------------------------------

/** Thrown when a placement action needs a connected Gmail account and there
 * isn't one -- distinct from NotOnboardedError, which is about the profile. */
export class GmailNotConnectedError extends Error {}

export const getPlacementStatus = () =>
  apiFetch<PlacementConnectionStatus>("/api/placement/status");

/** Opens the user's browser for the Google OAuth consent screen and blocks
 * until they approve or the request times out -- expect this call to take
 * as long as the user takes to click through the browser flow. */
export const connectGmail = () =>
  apiFetch<PlacementConnectionStatus>("/api/placement/connect", { method: "POST" });

export const disconnectGmail = () =>
  apiFetch<void>("/api/placement/disconnect", { method: "POST" });

/** Runs one sync: fetches new mail since the last sync, extracts candidate
 * matches and events, and files anything below the auto-accept confidence
 * into the review queue rather than acting on a guess. */
export async function syncPlacementMail(): Promise<void> {
  try {
    await apiFetch<void>("/api/placement/sync", { method: "POST" });
  } catch (err) {
    if (err instanceof Error && err.message.startsWith("412:")) {
      if (err.message.toLowerCase().includes("gmail")) {
        throw new GmailNotConnectedError("Gmail is not connected");
      }
      throw new NotOnboardedError("profile not onboarded yet");
    }
    throw err;
  }
}

export const listPlacementReviewQueue = () =>
  apiFetch<PlacementRecordOut[]>("/api/placement/review-queue");

export const confirmPlacementRecord = (recordId: number) =>
  apiFetch<PlacementRecordOut>(`/api/placement/review/${recordId}/confirm`, { method: "POST" });

export const rejectPlacementRecord = (recordId: number) =>
  apiFetch<void>(`/api/placement/review/${recordId}/reject`, { method: "POST" });

export const getPlacementTimeline = () => apiFetch<PlacementTimeline>("/api/placement/timeline");

// -- Career skill intelligence (spec §4) -------------------------------------

export async function listSkillGaps(): Promise<SkillGapOut[]> {
  try {
    return await apiFetch<SkillGapOut[]>("/api/career/skill-gaps");
  } catch (err) {
    if (err instanceof Error && err.message.startsWith("412:")) {
      throw new NotOnboardedError("profile not onboarded yet");
    }
    throw err;
  }
}

// -- Personalized cold outreach (spec §6) ------------------------------------

export async function listOutreachTargets(): Promise<OutreachTargetOut[]> {
  try {
    return await apiFetch<OutreachTargetOut[]>("/api/outreach/targets");
  } catch (err) {
    if (err instanceof Error && err.message.startsWith("412:")) {
      throw new NotOnboardedError("profile not onboarded yet");
    }
    throw err;
  }
}

export async function listOutreachDrafts(): Promise<OutreachDraftOut[]> {
  try {
    return await apiFetch<OutreachDraftOut[]>("/api/outreach/drafts");
  } catch (err) {
    if (err instanceof Error && err.message.startsWith("412:")) {
      throw new NotOnboardedError("profile not onboarded yet");
    }
    throw err;
  }
}

/** Generates (or regenerates) a draft for one resume/job pair -- always a
 * template fill from real match evidence, never sent by this app. */
export const createOutreachDraft = (data: DraftIn) =>
  apiFetch<OutreachDraftOut>("/api/outreach/drafts", { method: "POST", body: JSON.stringify(data) });

export const deleteOutreachDraft = (draftId: number) =>
  apiFetch<void>(`/api/outreach/drafts/${draftId}`, { method: "DELETE" });
