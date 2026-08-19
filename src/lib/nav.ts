import type { ComponentType, SVGProps } from "react";

import {
  BookIcon,
  CheckIcon,
  GroupsIcon,
  HomeIcon,
  ResumeDocIcon,
  SearchIcon,
  SettingsIcon,
} from "@/components/icons";

/** Left-hand navigation, in the order given at specification.md lines 812-826. */
export interface NavItem {
  path: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}

export const NAV_ITEMS: NavItem[] = [
  { path: "/", label: "Dashboard", icon: HomeIcon },
  { path: "/jobs", label: "Jobs", icon: SearchIcon },
  { path: "/resumes", label: "Resumes", icon: ResumeDocIcon },
  { path: "/tailor", label: "Tailor", icon: CheckIcon },
  { path: "/career", label: "Career", icon: BookIcon },
  { path: "/outreach", label: "Outreach", icon: GroupsIcon },
  { path: "/placement", label: "Placement", icon: GroupsIcon },
];

export const SETTINGS_ITEM: NavItem = { path: "/settings", label: "Settings", icon: SettingsIcon };
