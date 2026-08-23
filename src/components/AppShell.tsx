import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { NavLink, useLocation, useOutlet } from "react-router-dom";

import logo from "@/assets/logo.png";
import { DarkModeIcon, LightModeIcon, MenuIcon, PersonIcon } from "@/components/icons";
import { Switch } from "@/components/ui/switch";
import { getModelStatus, getProfile, NotOnboardedError } from "@/lib/api";
import { NAV_ITEMS, SETTINGS_ITEM, type NavItem } from "@/lib/nav";
import { useTheme } from "@/lib/theme";

/**
 * The application chrome: a single left column carrying the logo mark and
 * navigation, a floating theme toggle anchored to the page corner, and a
 * scrolling work area alongside the sidebar.
 *
 * Deliberately no separate top bar -- the reference this design follows
 * (docs/decisions.md#adr-0006--studio-visual-language-superseding-the-github-adjacent-direction) keeps navigation chrome in
 * one sidebar column. The theme toggle is the one control that lives outside
 * that column, fixed to the page rather than the sidebar, so it stays put
 * regardless of collapse state or which route is open.
 *
 * Only the workspace scrolls. The shell itself is desktop chrome and must
 * never move, which is why `body` carries `overflow: hidden` in
 * styles/index.css.
 */
export function AppShell() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="flex h-full flex-col">
      <ModelDownloadBanner />
      <div className="flex min-h-0 flex-1">
        <Sidebar collapsed={collapsed} onToggleCollapsed={() => setCollapsed((c) => !c)} />
        <main className="min-w-0 flex-1 overflow-y-auto">
          <PageTransition />
        </main>
        <ThemeToggle />
      </div>
    </div>
  );
}

// Same curve as --ease-out in styles/index.css -- Motion's transition prop
// takes a literal array, not a CSS var, so the value is duplicated here
// rather than forked into a different-looking one.
const EASE_OUT: [number, number, number, number] = [0.23, 1, 0.32, 1];

/**
 * First-run-only: the embedding model (M6, ADR 0005) downloads to disk the
 * first time the sidecar starts with no network cache yet. Polls
 * /api/matching/model-status every 2s only while not ready -- lightweight
 * and DB-free by design (see the endpoint's own docstring) -- and stops
 * polling for the rest of the session once ready, since the model never
 * becomes un-ready again short of a restart.
 *
 * Lives in the shell rather than any one route so it stays visible no
 * matter which page the user lands on -- a resume upload or job match on
 * any page can hit the same not-ready model.
 */
function ModelDownloadBanner() {
  const reduceMotion = useReducedMotion();
  const { data } = useQuery({
    queryKey: ["model-status"],
    queryFn: getModelStatus,
    refetchInterval: (query) => (query.state.data?.ready ? false : 2000),
  });

  const show = data?.downloading ?? false;
  const percent = Math.round((data?.approx_progress ?? 0) * 100);

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ opacity: 0, y: reduceMotion ? 0 : -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: reduceMotion ? 0 : -8 }}
          transition={{ duration: reduceMotion ? 0 : 0.2, ease: EASE_OUT }}
          className="flex shrink-0 items-center gap-3 border-b px-4 py-2 text-sm"
          style={{ borderColor: "var(--border)", background: "var(--accent-subtle)" }}
        >
          <span style={{ color: "var(--fg)" }}>
            Setting up the matching model (one-time download)&hellip;
          </span>
          <div
            className="h-1.5 w-40 shrink-0 overflow-hidden rounded-full"
            style={{ background: "var(--canvas-subtle)" }}
          >
            <div
              className="h-full w-full origin-left rounded-full"
              style={{
                background: "var(--accent)",
                transform: `scaleX(${data?.approx_progress ?? 0})`,
                transitionProperty: reduceMotion ? "none" : "transform",
                transitionDuration: "400ms",
                transitionTimingFunction: "var(--ease-out)",
              }}
            />
          </div>
          <span style={{ color: "var(--fg-muted)" }}>{percent}%</span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/**
 * Fades the leaving route out, then fades the arriving one in.
 *
 * useOutlet() (not <Outlet/>) is what makes an exit animation possible at
 * all: it hands back the matched route's element as a value, so the element
 * keyed to the *previous* location can keep rendering inside AnimatePresence
 * through its exit animation instead of being unmounted the instant the URL
 * changes. This replaced an earlier attempt built on the View Transitions
 * API, which never visibly fired -- AnimatePresence is the same tool this
 * app already relies on for the theme toggle's icon swap
 * (src/components/ui/switch.tsx), so it's the proven choice rather than a
 * browser API this codebase has no other working example of.
 */
function PageTransition() {
  const location = useLocation();
  const element = useOutlet();
  const reduceMotion = useReducedMotion();
  const duration = reduceMotion ? 0 : undefined;

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={location.pathname}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1, transition: { duration: duration ?? 0.16, ease: EASE_OUT } }}
        exit={{ opacity: 0, transition: { duration: duration ?? 0.12, ease: EASE_OUT } }}
      >
        {element}
      </motion.div>
    </AnimatePresence>
  );
}

function Sidebar({
  collapsed,
  onToggleCollapsed,
}: {
  collapsed: boolean;
  onToggleCollapsed: () => void;
}) {
  return (
    <nav
      className={`sidebar-rail flex shrink-0 flex-col border-r p-3 ${collapsed ? "w-16" : "w-60"}`}
      style={{ borderColor: "var(--border)", background: "var(--canvas)" }}
    >
      <Logo collapsed={collapsed} />

      <ul className="mt-6 flex flex-1 flex-col gap-1">
        {NAV_ITEMS.map((item) => (
          <SidebarLink key={item.path} item={item} collapsed={collapsed} />
        ))}
      </ul>

      {/* Profile sits directly above Settings -- identity and account
       * configuration read as one group. */}
      <ul className="flex flex-col gap-1">
        <ProfileLink collapsed={collapsed} />
        <SidebarLink item={SETTINGS_ITEM} collapsed={collapsed} />
      </ul>

      <div
        className="mt-3 flex justify-center border-t pt-3"
        style={{ borderColor: "var(--border)" }}
      >
        <button
          type="button"
          onClick={onToggleCollapsed}
          aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          aria-pressed={collapsed}
          className="icon-btn h-8 w-8 shrink-0 rounded-full"
          style={{ color: "var(--fg-muted)" }}
        >
          <MenuIcon className="mx-auto" width={16} height={16} />
        </button>
      </div>
    </nav>
  );
}

function Logo({ collapsed }: { collapsed: boolean }) {
  return (
    <div className="flex items-center gap-2.5 px-1 py-1">
      <img src={logo} alt="" className="h-7 w-7 shrink-0" aria-hidden="true" />
      <span className="sidebar-label" data-collapsed={collapsed}>
        <span
          className="block font-serif text-base font-semibold tracking-tight"
          style={{ color: "var(--fg)" }}
        >
          PlaceInator
        </span>
        <span className="eyebrow block" style={{ color: "var(--fg-subtle)" }}>
          Placement Companion
        </span>
      </span>
    </div>
  );
}

/** Shared row treatment for both nav links and the profile link.
 *
 * Collapsed sidebar content is 40px wide (w-16 minus the nav's own p-3).
 * The 28px badge (h-7 w-7) only fits inside that with near-zero horizontal
 * padding and centered justification -- the expanded row's px-2.5 was
 * previously left in place unconditionally, which overflowed the badge
 * past the sidebar's edge in collapsed mode. */
function navRowClassName(collapsed: boolean): string {
  // gap-2.5 must drop to gap-0 when collapsed: the label span stays mounted
  // (max-width: 0) rather than unmounting, so a nonzero gap still reserves
  // space after it even though it's invisible. With justify-center, that
  // reserved gap became part of the centered block and pushed the badge off
  // to the left of true center -- the badge, not the gap, needs to be the
  // only thing this row centers.
  const layout = collapsed ? "justify-center gap-0 px-1" : "gap-2.5 px-2.5";
  return `sidebar-row flex items-center rounded-2xl py-2 text-sm transition-colors ${layout}`;
}

function SidebarLink({ item, collapsed }: { item: NavItem; collapsed: boolean }) {
  const Icon = item.icon;
  return (
    <li>
      <NavLink
        to={item.path}
        // `end` keeps "/" from matching every route.
        end={item.path === "/"}
        title={collapsed ? item.label : undefined}
        className={navRowClassName(collapsed)}
        style={({ isActive }) => ({
          background: isActive ? "var(--canvas-subtle)" : "transparent",
          border: `1px solid ${isActive ? "var(--border)" : "transparent"}`,
          color: isActive ? "var(--fg)" : "var(--fg-muted)",
          fontWeight: isActive ? 600 : 500,
        })}
      >
        <span
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
          style={{ background: `color-mix(in srgb, var(${item.color}) 20%, transparent)` }}
        >
          <Icon width={16} height={16} style={{ color: `var(${item.color})` }} />
        </span>
        <span className="sidebar-label" data-collapsed={collapsed}>
          {item.label}
        </span>
      </NavLink>
    </li>
  );
}

function ProfileLink({ collapsed }: { collapsed: boolean }) {
  const { data: profile } = useQuery({
    queryKey: ["profile"],
    queryFn: getProfile,
    retry: (count, err) => !(err instanceof NotOnboardedError) && count < 2,
  });

  const label = profile?.full_name?.trim() || "Complete profile";

  return (
    <li>
      <NavLink
        to="/profile"
        title={collapsed ? label : undefined}
        className={navRowClassName(collapsed)}
        style={{ color: profile ? "var(--fg-muted)" : "var(--accent)", fontWeight: 500 }}
      >
        <span
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
          style={{
            background: profile
              ? "color-mix(in srgb, var(--fg-muted) 20%, transparent)"
              : "var(--accent-subtle)",
          }}
        >
          <PersonIcon width={16} height={16} />
        </span>
        <span className="sidebar-label truncate" data-collapsed={collapsed}>
          {label}
        </span>
      </NavLink>
    </li>
  );
}

function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";

  return (
    <div
      className="fixed right-4 top-4 z-10"
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
    >
      <Switch
        value={isDark}
        // The click's own coordinates anchor the circular reveal --
        // src/lib/theme.ts expands it from exactly this point.
        onToggle={(event) => toggleTheme({ x: event.clientX, y: event.clientY })}
        iconOn={<DarkModeIcon width={14} height={14} />}
        iconOff={<LightModeIcon width={14} height={14} />}
      />
    </div>
  );
}
