"use client";

import { useQuery } from "@tanstack/react-query";
import type { Tone } from "@/components/ui";
import { ACTIVE_RUN, api, type Approachability, type LeadOut, type Page } from "./api";

/** Every lead (the POC dataset is small), refreshed while an AI check is running. */
export function useLeads() {
  return useQuery({
    queryKey: ["leads-all"],
    queryFn: () => api<Page<LeadOut>>("/leads", { query: { limit: 200, sort: "newest" } }),
    refetchInterval: (q) => (q.state.data?.items.some((l) => ACTIVE_RUN.includes(l.latest_run?.status ?? "")) ? 2_000 : 15_000),
  });
}

export const reach = (l: LeadOut) => l.latest_recommendation?.approachability as Approachability | undefined;
export const topProduct = (l: LeadOut) => (l.latest_recommendation?.top_product as { code: string; name?: string } | null | undefined)?.name;

export const isChecked = (l: LeadOut) => !!l.latest_recommendation;
export const isEligible = (l: LeadOut) => ["contact_and_quote", "nurture"].includes(l.latest_recommendation?.action ?? "");
export const needsUnderwriter = (l: LeadOut) => l.latest_recommendation?.action === "refer_to_underwriter";
export type Label = { label: string; tone: Tone };

/** The prospect agent's call: may we approach this person at all? */
export function eligibility(l: LeadOut): Label & { key: "eligible" | "review" | "blocked" | "none" } {
  const a = l.latest_recommendation?.action;
  if (!a) return { key: "none", label: "Not assessed", tone: "gray" };
  if (a === "do_not_contact") return { key: "blocked", label: "No consent", tone: "red" };
  if (a === "request_info") return { key: "blocked", label: "Missing details", tone: "amber" };
  if (a === "refer_to_underwriter") return { key: "review", label: "Underwriter review", tone: "amber" };
  return { key: "eligible", label: "Eligible", tone: "green" };
}

/** Where the staff decision on the latest recommendation stands. */
export const REC_STATUS: Record<string, Label> = {
  pending_approval: { label: "Awaiting approval", tone: "amber" },
  approved: { label: "Approved", tone: "green" },
  approved_with_edits: { label: "Approved", tone: "green" },
  rejected: { label: "Rejected", tone: "red" },
  superseded: { label: "Replaced", tone: "gray" },
  expired: { label: "Expired", tone: "gray" },
};

export const PRIORITY: Record<string, Label> = {
  high: { label: "High", tone: "red" },
  medium: { label: "Medium", tone: "amber" },
  low: { label: "Low", tone: "blue" },
};

/** How the customer is reached: directly, or only through the broker / employer / adviser. */
export const contactRoute = (l: LeadOut) => (l.channel_owner === "direct" ? "Direct" : `Via ${l.channel_owner}${l.intermediary ? ` · ${l.intermediary}` : ""}`);
