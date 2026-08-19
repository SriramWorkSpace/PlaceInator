import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router-dom";

import { DarkModeIcon, LightModeIcon, MenuIcon, PersonIcon } from "@/components/icons";
import { getProfile, NotOnboardedError } from "@/lib/api";
import { NAV_ITEMS, SETTINGS_ITEM, type NavItem } from "@/lib/nav";
import { useTheme } from "@/lib/theme";

/**
 * The application chrome: a single left column carrying the logo mark and
 * navigation, a floating theme toggle anchored to the page corner, and a
 * scrolling work area alongside the sidebar.
 *
 * Deliberately no separate top bar -- the reference this design follows
 * (docs/decisions/0006-studio-visual-language.md) keeps navigation chrome in
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
    <div className="flex h-full">
      <Sidebar collapsed={collapsed} onToggleCollapsed={() => setCollapsed((c) => !c)} />
      <main className="min-w-0 flex-1 overflow-y-auto">
        <Outlet />
      </main>
      <ThemeToggle />
    </div>
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
      <span
        className="h-6 w-6 shrink-0 rotate-45 rounded-[6px]"
        style={{ background: "var(--accent)" }}
        aria-hidden="true"
      />
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
  const padding = collapsed ? "justify-center px-1" : "px-2.5";
  return `sidebar-row flex items-center gap-2.5 rounded-2xl py-2 text-sm transition-colors ${padding}`;
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
        to="/settings"
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
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      aria-pressed={isDark}
      className="icon-btn fixed right-4 top-4 z-10 h-9 w-9 rounded-full border"
      style={{ color: "var(--fg-muted)", borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
    >
      {/* Both icons stay mounted so the swap is a CSS transition, not a
       * remount -- required for a control the user can click rapidly. */}
      <span className="theme-icon" data-hidden={!isDark}>
        <LightModeIcon width={18} height={18} />
      </span>
      <span className="theme-icon" data-hidden={isDark}>
        <DarkModeIcon width={18} height={18} />
      </span>
    </button>
  );
}
