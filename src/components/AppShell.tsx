import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { DarkModeIcon, LightModeIcon, MenuIcon, PersonIcon } from "@/components/icons";
import { getProfile, NotOnboardedError } from "@/lib/api";
import { NAV_ITEMS, SETTINGS_ITEM, type NavItem } from "@/lib/nav";
import { useTheme } from "@/lib/theme";

/**
 * The application chrome: top bar, fixed left navigation, and a scrolling work
 * area (specification.md lines 812-826).
 *
 * Only the workspace scrolls. The shell itself is desktop chrome and must never
 * move, which is why `body` carries `overflow: hidden` in styles/index.css.
 */
export function AppShell() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="flex h-full flex-col">
      <TopBar collapsed={collapsed} onToggleCollapsed={() => setCollapsed((c) => !c)} />
      <div className="flex min-h-0 flex-1">
        <Sidebar collapsed={collapsed} />
        <main className="min-w-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function TopBar({
  collapsed,
  onToggleCollapsed,
}: {
  collapsed: boolean;
  onToggleCollapsed: () => void;
}) {
  return (
    <header
      className="flex h-12 shrink-0 items-center gap-3 border-b px-4"
      style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
    >
      <button
        type="button"
        onClick={onToggleCollapsed}
        aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
        aria-pressed={collapsed}
        className="icon-btn -ml-1 rounded p-1"
        style={{ color: "var(--fg-muted)" }}
      >
        <MenuIcon />
      </button>
      <span className="text-sm font-semibold tracking-tight">PlaceInator</span>
      <div className="flex-1" />
      <ThemeToggle />
      <ProfileButton />
    </header>
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
      className="icon-btn relative h-7 w-7 shrink-0 rounded"
      style={{ color: "var(--fg-muted)" }}
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

function ProfileButton() {
  const navigate = useNavigate();
  const { data: profile } = useQuery({
    queryKey: ["profile"],
    queryFn: getProfile,
    retry: (count, err) => !(err instanceof NotOnboardedError) && count < 2,
  });

  const label = profile?.full_name?.trim() || "Complete profile";

  return (
    <button
      type="button"
      onClick={() => navigate("/settings")}
      className="icon-btn flex shrink-0 items-center gap-1.5 rounded px-1.5 py-1 text-xs font-medium"
      style={{ color: profile ? "var(--fg-muted)" : "var(--accent)" }}
      title={profile ? profile.email : "Onboarding not complete"}
    >
      <PersonIcon width={18} height={18} />
      <span className="max-w-32 truncate">{label}</span>
    </button>
  );
}

function Sidebar({ collapsed }: { collapsed: boolean }) {
  return (
    <nav
      className={`flex shrink-0 flex-col justify-between border-r p-2 transition-[width] ${collapsed ? "w-14" : "w-52"}`}
      style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
    >
      <ul className="flex flex-col gap-0.5">
        {NAV_ITEMS.map((item) => (
          <SidebarLink key={item.path} item={item} collapsed={collapsed} />
        ))}
      </ul>
      <ul className="flex flex-col gap-0.5">
        <SidebarLink item={SETTINGS_ITEM} collapsed={collapsed} />
      </ul>
    </nav>
  );
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
        className="flex items-center gap-2.5 rounded px-2.5 py-1.5 text-sm transition-colors"
        style={({ isActive }) => ({
          background: isActive ? "var(--accent-subtle)" : "transparent",
          color: isActive ? "var(--accent)" : "var(--fg-muted)",
          fontWeight: isActive ? 600 : 400,
        })}
      >
        <Icon className="shrink-0" width={18} height={18} />
        {!collapsed && <span>{item.label}</span>}
      </NavLink>
    </li>
  );
}
