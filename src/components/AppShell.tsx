import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  animate as animateValue,
  AnimatePresence,
  motion,
  useMotionValue,
  useReducedMotion,
} from "motion/react";
import { NavLink, useLocation, useOutlet } from "react-router-dom";

import logo from "@/assets/logo.png";
import { DarkModeIcon, LightModeIcon, MenuIcon, PersonIcon } from "@/components/icons";
import { Switch } from "@/components/ui/switch";
import { getModelStatus, getPlacementStatus, getProfile, NotOnboardedError, syncPlacementMail } from "@/lib/api";
import { NAV_ITEMS, navItemForPath, PROFILE_ITEM, SETTINGS_ITEM, type NavItem } from "@/lib/nav";
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
  // Starts minimized (icon-only) on every launch, including the very
  // first frame -- expands only on an explicit pin-toggle click or a
  // hover-peek (Sidebar's own `hovering` state), never by default.
  const [collapsed, setCollapsed] = useState(true);

  return (
    <div className="flex h-full flex-col">
      <ModelDownloadBanner />
      <AutoPlacementSync />
      <div className="flex min-h-0 flex-1">
        <Sidebar pinnedCollapsed={collapsed} onToggleCollapsed={() => setCollapsed((c) => !c)} />
        <main className="min-w-0 flex-1 overflow-y-auto">
          <PageTransition />
        </main>
        <ThemeToggle />
      </div>
    </div>
  );
}

/**
 * Runs one placement-mail sync automatically the moment the app opens,
 * instead of making the user find Placement and click "Sync now" first.
 * Lives here (not in Placement.tsx's own SyncControl) because AppShell
 * mounts exactly once per app session -- routes swap inside it via
 * PageTransition's outlet without remounting the shell -- so this fires
 * once per launch regardless of which page the user lands on.
 *
 * Silent by design: a background sync failing (stale token, offline) isn't
 * something the user needs interrupted for before they've done anything --
 * Placement's own "Sync now" still surfaces errors for a manual retry.
 * `syncedRef` (not just the query's own cache) guards against firing twice
 * from React 18 Strict Mode's double-invoked effects in dev.
 */
function AutoPlacementSync() {
  const queryClient = useQueryClient();
  const { data: status } = useQuery({
    queryKey: ["placement", "status"],
    queryFn: getPlacementStatus,
  });
  const syncedRef = useRef(false);

  useEffect(() => {
    if (!status?.connected || syncedRef.current) return;
    syncedRef.current = true;
    syncPlacementMail()
      .then(() => queryClient.invalidateQueries({ queryKey: ["placement"] }))
      .catch(() => {});
  }, [status?.connected, queryClient]);

  return null;
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

type Rect = { top: number; left: number; width: number; height: number };

// Occasional (click-driven navigation): a touch of spring personality reads
// as "the selection landed here" rather than a mechanical slide.
const ACTIVE_PILL_TRANSITION = { type: "spring", bounce: 0.18, duration: 0.35 } as const;
// Tens of times a session (every pointer move across the rail): non-bouncy
// and fast, so it stays a clean glide instead of a twitchy overshoot.
const HOVER_PILL_TRANSITION = { duration: 0.15, ease: EASE_OUT } as const;
// A little past .sidebar-rail's own 200ms CSS width transition (see
// styles/index.css) -- the extra margin is slack against timing jitter, not
// a second animation duration (see the resize-tracking effect below, which
// doesn't animate at all, just samples).
const RESIZE_TRACK_DURATION_MS = 240;

/**
 * `pinnedCollapsed` is the persisted preference (the toggle button at the
 * bottom flips this). `hovering` is a separate, ephemeral peek: resting the
 * pointer over a pinned-collapsed rail expands it temporarily -- same
 * pattern as VS Code's/Notion's collapsed sidebars -- without touching the
 * persisted state, so moving the pointer away collapses it right back. The
 * two combine into one `expanded` boolean that everything below (labels,
 * row padding, the logo) already keys off via the existing `collapsed` prop
 * shape, so hovering and the explicit toggle both drive the exact same
 * animation path rather than two different ones.
 *
 * The active/hover highlights are two persistent elements (never unmounted
 * while in use) positioned via Motion values (top/left/width/height) read
 * from each row's own `offsetTop/Left/Width/Height` -- see `measure()`.
 * Route changes and hover moves *animate* those values with Motion's
 * `animate()` (ACTIVE/HOVER_PILL_TRANSITION). Collapsing/expanding the rail
 * is handled differently and deliberately does NOT use `animate()`: earlier
 * versions tried re-measuring once (on transitionend) or periodically (a
 * ResizeObserver) and replaying a *separate*, same-duration Motion tween
 * alongside .sidebar-rail's own 200ms CSS width transition -- two
 * independently-timed animations approximating each other are never
 * perfectly locked, and in practice the pill visibly lagged behind the
 * rail's own resize before catching up. The resize-tracking effect below
 * instead samples the row's live layout on every animation frame for the
 * duration of the CSS transition and writes it straight to the Motion
 * values with `.set()` (no easing of its own) -- the pill's motion is
 * therefore *sampled from* the CSS transition's own curve, frame by frame,
 * rather than a second animation racing to approximate it.
 */
function Sidebar({
  pinnedCollapsed,
  onToggleCollapsed,
}: {
  pinnedCollapsed: boolean;
  onToggleCollapsed: () => void;
}) {
  const [hovering, setHovering] = useState(false);
  const expanded = !pinnedCollapsed || hovering;
  const collapsed = !expanded;
  const reduceMotion = useReducedMotion();
  const location = useLocation();

  const navGroupRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef(new Map<string, HTMLElement>());
  // The path currently under the pointer, kept independent of React state so
  // the resize-tracking effect can keep reading it without waiting for a
  // fresh mouseenter -- collapsing/expanding never fires one, since the
  // pointer doesn't actually move when the rail resizes under it.
  const hoveredPathRef = useRef<string | null>(null);

  const activeTop = useMotionValue(0);
  const activeLeft = useMotionValue(0);
  const activeWidth = useMotionValue(0);
  const activeHeight = useMotionValue(0);
  const hoverTop = useMotionValue(0);
  const hoverLeft = useMotionValue(0);
  const hoverWidth = useMotionValue(0);
  const hoverHeight = useMotionValue(0);
  const [activeVisible, setActiveVisible] = useState(false);
  const [hoverVisible, setHoverVisible] = useState(false);

  const activePath = navItemForPath(location.pathname)?.path ?? null;

  function measure(path: string | null): Rect | null {
    const container = navGroupRef.current;
    const el = path ? rowRefs.current.get(path) : undefined;
    if (!container || !el) return null;
    return { top: el.offsetTop, left: el.offsetLeft, width: el.offsetWidth, height: el.offsetHeight };
  }

  function rectForHover(path: string | null): Rect | null {
    // Skip showing a hover highlight on the row that's already active --
    // the active pill alone is enough; a second highlight stacked on it
    // would just look like a doubled border.
    return path && path !== activePath ? measure(path) : null;
  }

  function setInstantly(rect: Rect, mv: { top: typeof activeTop; left: typeof activeLeft; width: typeof activeWidth; height: typeof activeHeight }) {
    mv.top.set(rect.top);
    mv.left.set(rect.left);
    mv.width.set(rect.width);
    mv.height.set(rect.height);
  }

  function animateTo(rect: Rect, mv: { top: typeof activeTop; left: typeof activeLeft; width: typeof activeWidth; height: typeof activeHeight }, transition: object) {
    if (reduceMotion) {
      setInstantly(rect, mv);
      return;
    }
    animateValue(mv.top, rect.top, transition);
    animateValue(mv.left, rect.left, transition);
    animateValue(mv.width, rect.width, transition);
    animateValue(mv.height, rect.height, transition);
  }

  const activeMV = { top: activeTop, left: activeLeft, width: activeWidth, height: activeHeight };
  const hoverMV = { top: hoverTop, left: hoverLeft, width: hoverWidth, height: hoverHeight };

  // Runs before paint (not useEffect) so the active pill is already in the
  // right place on first render/route change instead of flashing in a frame
  // late. Measuring a DOM node's own layout (offsetTop and friends) is one
  // of the few things that genuinely cannot be computed during render -- the
  // row has to have been painted first -- so this is the textbook
  // "synchronize with an external system" use of an effect, not derived
  // state that belongs in render.
  useLayoutEffect(() => {
    const rect = measure(activePath);
    if (!rect) return;
    if (activeVisible) {
      animateTo(rect, activeMV, ACTIVE_PILL_TRANSITION);
    } else {
      // First-ever measurement: appear already in place, no animating in
      // from the coordinate-origin default the motion values start at.
      setInstantly(rect, activeMV);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setActiveVisible(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePath]);

  // Collapsing/expanding resizes every row (a wide labeled pill vs. a 40px
  // icon-only square) over .sidebar-rail's own 200ms CSS width transition,
  // without the pointer ever moving -- nothing else re-measures a highlight
  // mid-transition. Sampling the live layout every animation frame for the
  // transition's duration and writing it straight to the Motion values
  // (`.set()`, not `.animate()`) is what keeps the highlight glued to the
  // row instead of a second, separately-timed animation trying to catch up
  // to it after the fact.
  useEffect(() => {
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const activeRect = measure(activePath);
      if (activeRect) setInstantly(activeRect, activeMV);
      const hoverRect = rectForHover(hoveredPathRef.current);
      if (hoverRect) setInstantly(hoverRect, hoverMV);
      if (now - start < RESIZE_TRACK_DURATION_MS) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collapsed]);

  // Collects each row's DOM node into rowRefs so `measure()` above can read
  // its layout on demand. The mutation happens inside the closure React
  // invokes as the ref callback (outside render, during commit) even
  // though `registerRow(path)` itself is called from JSX during render to
  // produce that closure.
  function registerRow(path: string) {
    return (el: HTMLElement | null) => {
      // Ref mutation inside the callback React invokes during commit, not render.
      // eslint-disable-next-line react-hooks/refs
      if (el) rowRefs.current.set(path, el);
      else rowRefs.current.delete(path);
    };
  }

  function handleHoverStart(path: string) {
    hoveredPathRef.current = path;
    const rect = rectForHover(path);
    if (!rect) {
      setHoverVisible(false);
      return;
    }
    if (hoverVisible) {
      animateTo(rect, hoverMV, HOVER_PILL_TRANSITION);
    } else {
      setInstantly(rect, hoverMV);
      setHoverVisible(true);
    }
  }

  function handleHoverEnd() {
    hoveredPathRef.current = null;
    setHoverVisible(false);
  }

  return (
    <nav
      className={`sidebar-rail flex shrink-0 flex-col border-r p-3 ${collapsed ? "w-16" : "w-60"}`}
      style={{ borderColor: "var(--border)", background: "var(--canvas)" }}
      onMouseEnter={() => pinnedCollapsed && setHovering(true)}
      onMouseLeave={() => setHovering(false)}
    >
      <Logo collapsed={collapsed} />

      {/* isolate: keeps the two absolutely-positioned pills (negative
       * z-index) painting below this group's own row content without
       * bleeding into an ancestor's stacking context -- same technique as
       * .btn's hover-fill circle in styles/index.css. One shared relative
       * container for both row lists (not one each) is what lets the hover
       * pill glide continuously from the nav-items list into the
       * profile/settings list rather than resetting at the boundary. */}
      <div ref={navGroupRef} className="relative isolate mt-6 flex flex-1 flex-col" onMouseLeave={handleHoverEnd}>
        {activeVisible && (
          <motion.div
            className="pointer-events-none absolute -z-10 rounded-full border"
            style={{
              background: "var(--accent-subtle)",
              borderColor: "var(--accent)",
              top: activeTop,
              left: activeLeft,
              width: activeWidth,
              height: activeHeight,
            }}
          />
        )}
        <AnimatePresence>
          {hoverVisible && (
            <motion.div
              className="pointer-events-none absolute -z-10 rounded-full"
              style={{
                background: "var(--canvas-inset)",
                top: hoverTop,
                left: hoverLeft,
                width: hoverWidth,
                height: hoverHeight,
              }}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: reduceMotion ? 0 : 0.15 }}
            />
          )}
        </AnimatePresence>

        <ul className="flex flex-1 flex-col gap-1">
          {NAV_ITEMS.map((item) => (
            <SidebarLink
              key={item.path}
              item={item}
              collapsed={collapsed}
              isActive={activePath === item.path}
              registerRow={registerRow(item.path)}
              onHover={() => handleHoverStart(item.path)}
            />
          ))}
        </ul>

        {/* Profile sits directly above Settings -- identity and account
         * configuration read as one group. */}
        <ul className="flex flex-col gap-1">
          <ProfileLink
            collapsed={collapsed}
            isActive={activePath === PROFILE_ITEM.path}
            registerRow={registerRow(PROFILE_ITEM.path)}
            onHover={() => handleHoverStart(PROFILE_ITEM.path)}
          />
          <SidebarLink
            item={SETTINGS_ITEM}
            collapsed={collapsed}
            isActive={activePath === SETTINGS_ITEM.path}
            registerRow={registerRow(SETTINGS_ITEM.path)}
            onHover={() => handleHoverStart(SETTINGS_ITEM.path)}
          />
        </ul>
      </div>

      <div
        className="mt-3 flex justify-center border-t pt-3"
        style={{ borderColor: "var(--border)" }}
      >
        <button
          type="button"
          onClick={onToggleCollapsed}
          aria-label={pinnedCollapsed ? "Expand navigation" : "Collapse navigation"}
          aria-pressed={pinnedCollapsed}
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
  // rounded-full (not rounded-2xl): at this row's height that renders as a
  // full stadium shape, so the highlight's end curves flow with the
  // circular icon badge instead of a squarer corner sitting oddly next to
  // a perfect circle. Collapsed rows get an explicit 40px square (h-10 w-10,
  // matching the 40px content width above) instead of content-driven
  // sizing -- content-driven width (~36px) vs. height (~44px from the icon
  // plus py-2) weren't equal, so rounded-full rendered a slight oval around
  // the icon rather than a true circle.
  const layout = collapsed ? "h-10 w-10 mx-auto justify-center" : "gap-2.5 px-2.5 py-2";
  return `sidebar-row flex items-center rounded-full text-sm transition-colors ${layout}`;
}

function SidebarLink({
  item,
  collapsed,
  isActive,
  registerRow,
  onHover,
}: {
  item: NavItem;
  collapsed: boolean;
  isActive: boolean;
  registerRow: (el: HTMLElement | null) => void;
  onHover: () => void;
}) {
  const Icon = item.icon;
  return (
    <li ref={registerRow}>
      <NavLink
        to={item.path}
        // `end` keeps "/" from matching every route.
        end={item.path === "/"}
        title={collapsed ? item.label : undefined}
        onMouseEnter={onHover}
        className={navRowClassName(collapsed)}
        style={{
          color: isActive ? "var(--accent)" : "var(--fg-muted)",
          fontWeight: isActive ? 600 : 500,
        }}
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

function ProfileLink({
  collapsed,
  isActive,
  registerRow,
  onHover,
}: {
  collapsed: boolean;
  isActive: boolean;
  registerRow: (el: HTMLElement | null) => void;
  onHover: () => void;
}) {
  const { data: profile } = useQuery({
    queryKey: ["profile"],
    queryFn: getProfile,
    retry: (count, err) => !(err instanceof NotOnboardedError) && count < 2,
  });

  const label = profile?.full_name?.trim() || "Complete profile";

  return (
    <li ref={registerRow}>
      <NavLink
        to="/profile"
        title={collapsed ? label : undefined}
        onMouseEnter={onHover}
        className={navRowClassName(collapsed)}
        style={{
          color: isActive || !profile ? "var(--accent)" : "var(--fg-muted)",
          fontWeight: isActive ? 600 : 500,
        }}
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
      // top-[68px]: fixed positioning measures from the whole window, not
      // AppShell's own box, and the custom TitleBar (App.tsx) now occupies
      // the top 36px (h-9) -- top-4 alone would sit inside that strip and
      // collide with its minimize/maximize/close buttons.
      className="fixed top-[68px] right-4 z-10"
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
