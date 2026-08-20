import { useCallback, useLayoutEffect, useSyncExternalStore } from "react";

export const PALETTES = ["violet", "ocean", "meadow", "terracotta"] as const;
export type Palette = (typeof PALETTES)[number];

const STORAGE_KEY = "placeinator-palette";

function storedPalette(): Palette {
  const value = localStorage.getItem(STORAGE_KEY);
  return (PALETTES as readonly string[]).includes(value ?? "") ? (value as Palette) : "violet";
}

function applyPalette(palette: Palette): void {
  // "violet" is the implicit default -- it's what :root already defines with
  // no attribute present -- so clear the attribute instead of writing it,
  // keeping the DOM clean for the common (unchanged) case.
  if (palette === "violet") {
    delete document.documentElement.dataset.palette;
  } else {
    document.documentElement.dataset.palette = palette;
  }
}

// Module-level store, not per-component useState -- same reasoning as
// src/lib/theme.ts: usePalette() is called from more than one place at once
// (the Settings page today; anywhere else later), and independent useState
// instances would desync from each other the moment one of them changes.
let currentPalette: Palette = storedPalette();
const listeners = new Set<() => void>();

function getSnapshot(): Palette {
  return currentPalette;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function setCurrentPalette(next: Palette): void {
  currentPalette = next;
  for (const listener of listeners) listener();
}

/**
 * Accent-color theme, independent of the light/dark toggle (see
 * src/lib/theme.ts) -- swaps only --accent/--accent-fg/--accent-subtle (see
 * styles/index.css), so every other token (canvas, borders, section colors)
 * stays fixed regardless of palette. Persisted the same way theme is: an
 * inline script in index.html applies the saved choice before first paint,
 * so there's no flash of the default palette on load.
 */
export function usePalette(): { palette: Palette; setPalette: (next: Palette) => void } {
  const palette = useSyncExternalStore(subscribe, getSnapshot);

  useLayoutEffect(() => {
    applyPalette(palette);
  }, [palette]);

  const setPalette = useCallback((next: Palette) => {
    setCurrentPalette(next);
    localStorage.setItem(STORAGE_KEY, next);
  }, []);

  return { palette, setPalette };
}
