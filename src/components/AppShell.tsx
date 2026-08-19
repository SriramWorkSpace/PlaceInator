import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { MenuIcon } from "@/components/icons";
import { NAV_ITEMS, SETTINGS_ITEM, type NavItem } from "@/lib/nav";

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
        className="-ml-1 rounded p-1 transition-colors hover:opacity-80"
        style={{ color: "var(--fg-muted)" }}
      >
        <MenuIcon />
      </button>
      <span className="text-sm font-semibold tracking-tight">PlaceInator</span>
      <div className="flex-1" />
      <span className="font-mono text-xs" style={{ color: "var(--fg-subtle)" }}>
        v0.1.0
      </span>
    </header>
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
