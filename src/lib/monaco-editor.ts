/**
 * Configures @monaco-editor/react to use the *locally bundled* monaco-editor
 * package rather than its default behavior: @monaco-editor/loader's own
 * config (verified directly, not assumed) points `paths.vs` at
 * `cdn.jsdelivr.net` and fetches the editor from there at runtime.
 *
 * That default is a real problem for this app specifically -- PlaceInator is
 * explicitly offline-first (ADR 0002/ADR 0005: "fully offline, zero API
 * cost, no user data leaves the machine"). A CDN-loaded editor would leave
 * the Tailor page silently broken with no network, exactly the failure mode
 * the rest of the app is built to avoid.
 *
 * `loader.config({ monaco })` points it at the already-imported local
 * package instead. Monaco also needs a worker for its editing/tokenization
 * services; Vite's `?worker` suffix imports the prebuilt worker entry
 * directly from node_modules, no extra plugin required.
 *
 * Only ever imported from inside Tailor.tsx's lazy chunk (see its
 * `lazy(() => import("@/lib/monaco-editor"))`), so monaco-editor's real
 * weight is never paid by any other route -- this module's side effects run
 * once, the first time that chunk loads.
 */
import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
import EditorWorker from "monaco-editor/editor/editor.worker?worker";

self.MonacoEnvironment = {
  getWorker: () => new EditorWorker(),
};

loader.config({ monaco });

export { default } from "@monaco-editor/react";
