/**
 * Reference usage example, as originally supplied (minus "use client",
 * which is a Next.js Server-Components directive with no meaning in this
 * Vite SPA -- harmless if left in, but confusing to a reader since it
 * implies a boundary that doesn't exist here). Not routed into the app.
 *
 * The real integration is the theme toggle in src/components/AppShell.tsx,
 * which uses this project's own DarkModeIcon/LightModeIcon (Material
 * Symbols, already used throughout the nav) instead of lucide-react's
 * Sun/Moon -- mixing two icon styles for one control would look
 * inconsistent next to everything else in the sidebar.
 */
import { useState } from "react";
import { Moon, Sun } from "lucide-react";

import { Switch } from "@/components/ui/switch";

export default function DemoSwitch() {
  const [darkMode, setDarkMode] = useState(false);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6" style={{ background: "var(--canvas)" }}>
      <h1 className="text-xl font-semibold">{darkMode ? "Dark Mode" : "Light Mode"}</h1>
      <Switch
        value={darkMode}
        onToggle={() => setDarkMode((prev) => !prev)}
        iconOn={<Moon className="size-4" />}
        iconOff={<Sun className="size-4" />}
      />
    </div>
  );
}
