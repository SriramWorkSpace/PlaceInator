/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Dev-only fallback for running the UI without the Tauri shell. */
  readonly VITE_SIDECAR_PORT?: string;
  readonly VITE_SIDECAR_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
