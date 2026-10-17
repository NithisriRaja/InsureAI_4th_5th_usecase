import {
  BadgePlus,
  BarChart3,
  LayoutDashboard,
  ListOrdered,
  MessageSquareText,
  PackageCheck,
  RefreshCcw,
  Search,
  ShieldAlert,
  Workflow,
} from "lucide-react";

/** Sidebar of the combined app: new customers (use case 4) first, then renewals (use case 5).
 *  Each half keeps its own pages, components and backend (/prospect and /renewal). */
export const PROSPECT_NAV = [
  { href: "/dashboard", label: "Prospect Dashboard", icon: BarChart3 },
  { href: "/prospects", label: "Prospect Discovery", icon: Search },
  { href: "/risk", label: "Risk Assessment", icon: ShieldAlert },
  { href: "/products", label: "Product Matching", icon: PackageCheck },
  { href: "/priorities", label: "Lead Prioritization", icon: ListOrdered },
  { href: "/engagement", label: "Sales Engagement", icon: MessageSquareText },
];

export const RENEWAL_NAV = [
  { href: "/renewal", label: "Renewals Dashboard", icon: LayoutDashboard },
  { href: "/renewal/renewals", label: "Renewal Management", icon: RefreshCcw },
  { href: "/renewal/retention", label: "Retention & Churn", icon: ShieldAlert },
  { href: "/renewal/cover", label: "Additional Cover", icon: BadgePlus },
  { href: "/renewal/workflow", label: "Workflow & Follow-ups", icon: Workflow },
];

/** The sidebar shows each use case under its own heading. `tone` is its dot colour (light enough for the dark sidebar). */
export const NAV_GROUPS = [
  { title: "New Customers", tone: "bg-[#60a5fa]", items: PROSPECT_NAV },
  { title: "Renewals & Retention", tone: "bg-[#34d399]", items: RENEWAL_NAV },
];

export const NAV = [...PROSPECT_NAV, ...RENEWAL_NAV];

export const APP_TAGLINE = "New Customers & Renewals";
