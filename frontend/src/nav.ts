import {
  BarChart3,
  FilePlus2,
  MessageSquareText,
  PackageCheck,
  Search,
} from "lucide-react";

/** Sidebar: new customers (use case 4). */
export const PROSPECT_NAV = [
  { href: "/apply", label: "New Application", icon: FilePlus2 },
  { href: "/dashboard", label: "Prospect Dashboard", icon: BarChart3 },
  { href: "/prospects", label: "Prospect Discovery", icon: Search },
  { href: "/products", label: "Product Matching", icon: PackageCheck },
  { href: "/engagement", label: "Sales Engagement", icon: MessageSquareText },
];

/** The sidebar shows the use case under its own heading. `tone` is its dot colour (light enough for the dark sidebar). */
export const NAV_GROUPS = [
  { title: "New Customers", tone: "bg-[#60a5fa]", items: PROSPECT_NAV },
];

export const NAV = [...PROSPECT_NAV];

export const APP_TAGLINE = "New Customers";
