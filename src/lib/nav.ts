import type { ComponentType, SVGProps } from "react";

import {
  BookIcon,
  CheckIcon,
  GroupsIcon,
  HomeIcon,
  PersonIcon,
  PlacementIcon,
  ResumeDocIcon,
  SearchIcon,
  SettingsIcon,
} from "@/components/icons";

/** Left-hand navigation, in the order given at specification.md lines 812-826. */
export interface NavItem {
  path: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  /** CSS custom property name (without var()) driving this section's badge
   * and eyebrow-label color -- see the --section-* tokens in index.css. */
  color: string;
}

export const NAV_ITEMS: NavItem[] = [
  { path: "/", label: "Dashboard", icon: HomeIcon, color: "--section-dashboard" },
  { path: "/jobs", label: "Jobs", icon: SearchIcon, color: "--section-jobs" },
  { path: "/resumes", label: "Resumes", icon: ResumeDocIcon, color: "--section-resumes" },
  { path: "/tailor", label: "Tailor", icon: CheckIcon, color: "--section-tailor" },
  { path: "/career", label: "Career", icon: BookIcon, color: "--section-career" },
  { path: "/outreach", label: "Outreach", icon: GroupsIcon, color: "--section-outreach" },
  { path: "/placement", label: "Placement", icon: PlacementIcon, color: "--section-placement" },
];

export const PROFILE_ITEM: NavItem = {
  path: "/profile",
  label: "Profile",
  icon: PersonIcon,
  color: "--fg-muted",
};

export const SETTINGS_ITEM: NavItem = {
  path: "/settings",
  label: "Settings",
  icon: SettingsIcon,
  color: "--fg-muted",
};

/** Look up which nav item a route belongs to, for Page's eyebrow label --
 * so every route gets a matching "SECTION" label and accent color from one
 * source of truth instead of passing them in at each call site. */
export function navItemForPath(pathname: string): NavItem | undefined {
  return [...NAV_ITEMS, PROFILE_ITEM, SETTINGS_ITEM].find((i) =>
    i.path === "/" ? pathname === "/" : pathname.startsWith(i.path),
  );
}
