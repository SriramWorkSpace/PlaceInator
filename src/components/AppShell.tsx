import { NavLink, Outlet } from "react-router-dom";

import { NAV_ITEMS, SETTINGS_ITEM, type NavItem } from "@/lib/nav";

/**
 * The application chrome: top bar, fixed left navigation, and a scrolling work
 * area (specification.md lines 812-826).
 *
 * Only the workspace scrolls. The shell itself is desktop chrome and must never
 * move, which is why `body` carries `overflow: hidden` in styles/index.css.
 */
export function AppShell() {
  return (
    <div className="flex h-full flex-col">
      <TopBar />
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <main className="min-w-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function TopBar() {
  return (
    <header
      className="flex h-12 shrink-0 items-center gap-4 border-b px-4"
      style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
    >
      <span className="text-sm font-semibold tracking-tight">PlaceInator</span>
      <div className="flex-1" />
      <span className="font-mono text-xs" style={{ color: "var(--fg-subtle)" }}>
        v0.1.0
      </span>
    </header>
  );
}

function Sidebar() {
  return (
    <nav
      className="flex w-52 shrink-0 flex-col justify-between border-r p-2"
      style={{ borderColor: "var(--border)", background: "var(--canvas-subtle)" }}
    >
      <ul className="flex flex-col gap-0.5">
        {NAV_ITEMS.map((item) => (
          <SidebarLink key={item.path} item={item} />
        ))}
      </ul>
      <ul className="flex flex-col gap-0.5">
        <SidebarLink item={SETTINGS_ITEM} />
      </ul>
    </nav>
  );
}

function SidebarLink({ item }: { item: NavItem }) {
  return (
    <li>
      <NavLink
        to={item.path}
        // `end` keeps "/" from matching every route.
        end={item.path === "/"}
        className="block rounded px-3 py-1.5 text-sm transition-colors"
        style={({ isActive }) => ({
          background: isActive ? "var(--accent-subtle)" : "transparent",
          color: isActive ? "var(--accent)" : "var(--fg-muted)",
          fontWeight: isActive ? 600 : 400,
        })}
      >
        {item.label}
      </NavLink>
    </li>
  );
}
