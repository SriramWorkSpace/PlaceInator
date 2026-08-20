import { useCallback, useLayoutEffect, useSyncExternalStore } from "react";
import { flushSync } from "react-dom";

type Theme = "light" | "dark";
type Origin = { x: number; y: number };

const STORAGE_KEY = "placeinator-theme";
const TRANSITION_DURATION_MS = 500;

function systemTheme(): Theme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function storedTheme(): Theme | null {
  const value = localStorage.getItem(STORAGE_KEY);
  return value === "light" || value === "dark" ? value : null;
}

function applyTheme(theme: Theme): void {
  // Matches the tokens in styles/index.css: an explicit data-theme wins over
  // the prefers-color-scheme media query.
  document.documentElement.dataset.theme = theme;
}

function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// Module-level store, not per-component useState: useTheme() is called from
// more than one place at once (AppShell's floating toggle, Settings'
// Appearance section), and each needs to see the other's change immediately.
// Independent useState instances would only agree after both happened to
// remount -- one toggle would silently desync the other's displayed switch
// position from the real (correctly-applied) DOM state. useSyncExternalStore
// is exactly React's mechanism for "one source of truth, several
// subscribers" without pulling in a state library for two small stores.
let currentTheme: Theme = storedTheme() ?? systemTheme();
const listeners = new Set<() => void>();

function getSnapshot(): Theme {
  return currentTheme;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function setCurrentTheme(next: Theme): void {
  currentTheme = next;
  for (const listener of listeners) listener();
}

/**
 * Explicit light/dark toggle, defaulting to the OS preference until the user
 * overrides it. The override persists across sessions via localStorage.
 *
 * `toggleTheme` optionally takes the toggle button's click coordinates and
 * plays the theme change as a circle expanding from that exact point, via
 * the View Transitions API. Two things make this actually work rather than
 * silently no-op:
 *
 * 1. `applyTheme` (the DOM mutation) runs in `useLayoutEffect`, not
 *    `useEffect`, and the state update that triggers it is wrapped in
 *    `flushSync`. `document.startViewTransition(callback)` needs the DOM to
 *    already reflect the new state by the time `callback` returns, so it can
 *    snapshot "before" and "after". A plain `useEffect` runs after paint --
 *    well after the transition would have already captured its snapshots --
 *    so the API would see no visual difference to animate. `flushSync`
 *    forces the synchronous commit path, which is what actually flushes a
 *    layout effect (not a passive one) within the callback -- this still
 *    works with useSyncExternalStore, since its re-render trigger is itself
 *    a React state update and so is included in what flushSync flushes.
 * 2. The API's own default is a plain crossfade; that's disabled in
 *    styles/index.css (`::view-transition-old/new(root) { animation: none }`)
 *    so only the clip-path circle below is visible.
 */
export function useTheme(): { theme: Theme; toggleTheme: (origin?: Origin) => void } {
  const theme = useSyncExternalStore(subscribe, getSnapshot);

  useLayoutEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const toggleTheme = useCallback((origin?: Origin) => {
    const next: Theme = currentTheme === "dark" ? "light" : "dark";
    const commit = () => {
      flushSync(() => {
        setCurrentTheme(next);
      });
      localStorage.setItem(STORAGE_KEY, next);
    };

    const supportsViewTransitions = "startViewTransition" in document;
    if (!supportsViewTransitions || !origin || prefersReducedMotion()) {
      commit();
      return;
    }

    const { x, y } = origin;
    const maxRadius = Math.hypot(
      Math.max(x, window.innerWidth - x),
      Math.max(y, window.innerHeight - y),
    );

    const transition = document.startViewTransition(commit);
    transition.ready
      .then(() => {
        document.documentElement.animate(
          {
            clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${maxRadius}px at ${x}px ${y}px)`],
          },
          {
            duration: TRANSITION_DURATION_MS,
            easing: "ease-in-out",
            pseudoElement: "::view-transition-new(root)",
          },
        );
      })
      .catch(() => {
        // transition.ready rejects if the transition is skipped (e.g. the
        // document became hidden mid-toggle); the theme itself already
        // committed via commit(), so there is nothing to recover here.
      });
  }, []);

  return { theme, toggleTheme };
}
