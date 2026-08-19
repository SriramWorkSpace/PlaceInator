/**
 * Client for the Python sidecar.
 *
 * The shell injects the handshake values on `window` before the app mounts. In
 * `vite dev` there is no shell, so we fall back to env vars — that fallback is
 * the only way to run the UI without a Rust toolchain installed.
 */

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

  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...init.headers,
    },
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
