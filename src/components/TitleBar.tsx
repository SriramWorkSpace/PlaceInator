import { useEffect, useState } from "react";
import { isTauri } from "@tauri-apps/api/core";
import { getCurrentWindow, type Window } from "@tauri-apps/api/window";

import logo from "@/assets/logo.png";

/**
 * Replaces the native OS title bar (tauri.conf.json sets `decorations:
 * false` on the main window specifically so this can exist) with one that
 * actually belongs to the app -- same canvas/border tokens as everything
 * else, instead of a plain dark strip sitting on top that never matched the
 * theme in either light or dark mode.
 *
 * `data-tauri-drag-region` on the background span is what makes the bar
 * draggable/double-click-to-maximize without any JS -- Tauri's own
 * convention (see @tauri-apps/api/window's docs). It must NOT be on the
 * button row, or dragging would swallow their clicks.
 *
 * getCurrentWindow() reads `window.__TAURI_INTERNALS__.metadata`, which
 * only exists inside the real Tauri WebView -- calling it in the
 * browser-only dev fallback (src/lib/api.ts's VITE_SIDECAR_* path, no Tauri
 * shell at all) throws immediately and previously crashed the whole app
 * before first paint (confirmed via a real Playwright run against the dev
 * server: "Cannot read properties of undefined (reading 'metadata')").
 * `isTauri()` is Tauri's own sanctioned runtime check for exactly this --
 * outside the shell, this renders a plain static bar with no window
 * controls (there's no native chrome to replace there anyway; the actual
 * browser tab already has its own).
 */
export function TitleBar() {
  const [appWindow] = useState<Window | null>(() => (isTauri() ? getCurrentWindow() : null));
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    if (!appWindow) return;
    appWindow.isMaximized().then(setMaximized).catch(() => {});
    const unlisten = appWindow.onResized(() => {
      appWindow.isMaximized().then(setMaximized).catch(() => {});
    });
    return () => {
      unlisten.then((fn) => fn()).catch(() => {});
    };
  }, [appWindow]);

  if (!appWindow) {
    return (
      <div
        className="flex h-9 shrink-0 items-center gap-2 border-b px-3 select-none"
        style={{ borderColor: "var(--border)", background: "var(--canvas)" }}
      >
        <img src={logo} alt="" className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span className="text-xs font-medium" style={{ color: "var(--fg-subtle)" }}>
          PlaceInator
        </span>
      </div>
    );
  }

  return (
    <div
      className="flex h-9 shrink-0 items-center justify-between border-b select-none"
      style={{ borderColor: "var(--border)", background: "var(--canvas)" }}
    >
      <span
        data-tauri-drag-region
        className="flex h-full flex-1 items-center gap-2 px-3"
        onDoubleClick={() => appWindow.toggleMaximize()}
      >
        <img src={logo} alt="" className="h-4 w-4 shrink-0" aria-hidden="true" data-tauri-drag-region />
        <span className="text-xs font-medium" style={{ color: "var(--fg-subtle)" }} data-tauri-drag-region>
          PlaceInator
        </span>
      </span>

      <div className="flex h-full shrink-0 items-center">
        <TitleBarButton label="Minimize" onClick={() => appWindow.minimize()}>
          <MinimizeGlyph />
        </TitleBarButton>
        <TitleBarButton label={maximized ? "Restore" : "Maximize"} onClick={() => appWindow.toggleMaximize()}>
          {maximized ? <RestoreGlyph /> : <MaximizeGlyph />}
        </TitleBarButton>
        <TitleBarButton label="Close" danger onClick={() => appWindow.close()}>
          <CloseGlyph />
        </TitleBarButton>
      </div>
    </div>
  );
}

function TitleBarButton({
  label,
  danger,
  onClick,
  children,
}: {
  label: string;
  danger?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="flex h-full w-11 items-center justify-center transition-colors"
      style={{ color: "var(--fg-muted)" }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = danger ? "var(--danger)" : "var(--canvas-inset)";
        e.currentTarget.style.color = danger ? "#ffffff" : "var(--fg)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "transparent";
        e.currentTarget.style.color = "var(--fg-muted)";
      }}
    >
      {children}
    </button>
  );
}

// Plain geometric strokes -- the universal minimize/maximize/restore/close
// glyphs every OS uses, not part of icons.tsx's Material Symbols fill-path
// set (a different icon language on purpose; window-chrome controls read as
// chrome, not as another app icon).
function MinimizeGlyph() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
      <line x1="0" y1="5" x2="10" y2="5" stroke="currentColor" strokeWidth="1" />
    </svg>
  );
}

function MaximizeGlyph() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
      <rect x="0.5" y="0.5" width="9" height="9" fill="none" stroke="currentColor" strokeWidth="1" />
    </svg>
  );
}

function RestoreGlyph() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
      <rect x="2.5" y="0.5" width="7" height="7" fill="none" stroke="currentColor" strokeWidth="1" />
      <path
        d="M0.5 2.5H7.5V9.5H0.5Z"
        style={{ fill: "var(--canvas)" }}
        stroke="currentColor"
        strokeWidth="1"
      />
    </svg>
  );
}

function CloseGlyph() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
      <line x1="0" y1="0" x2="10" y2="10" stroke="currentColor" strokeWidth="1" />
      <line x1="10" y1="0" x2="0" y2="10" stroke="currentColor" strokeWidth="1" />
    </svg>
  );
}
