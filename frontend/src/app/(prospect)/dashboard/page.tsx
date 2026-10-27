"use client";

import { AlertTriangle, ClipboardCheck, Flame, Users } from "lucide-react";
import { ColumnChart, Donut, PageHeader, Panel, RISK_COLOR, Stat } from "@/components/kit";
import { ErrorBox, Skeleton } from "@/components/ui";
import type { LeadOut } from "@/lib/api";
import { ACTION } from "@/lib/format";
import { isChecked, isEligible, needsUnderwriter, useLeads } from "@/lib/leads";

const isPending = (l: LeadOut) => l.latest_recommendation?.status === "pending_approval";

export default function DashboardPage() {
  const q = useLeads();
  if (q.isError) return <ErrorBox error={q.error} />;
  if (q.isPending) return <Skeleton className="h-96" />;

  const leads = q.data.items;
  const total = q.data.total;
  const checked = leads.filter(isChecked);
  const eligible = checked.filter(isEligible);
  const pending = checked.filter(isPending);
  const underwriter = checked.filter(needsUnderwriter);
  const hot = checked.filter((l) => l.latest_recommendation!.priority === "high");

  const priorities = [
    { label: "High priority", n: checked.filter((l) => l.latest_recommendation!.priority === "high").length, color: RISK_COLOR.high },
    { label: "Medium priority", n: checked.filter((l) => l.latest_recommendation!.priority === "medium").length, color: RISK_COLOR.medium },
    { label: "Low priority", n: checked.filter((l) => l.latest_recommendation!.priority === "low").length, color: RISK_COLOR.low },
  ];
  const actions = Object.keys(ACTION).map((a) => ({
    label: ACTION[a],
    n: checked.filter((l) => l.latest_recommendation!.action === a).length,
  }));
  const bands = [
    { label: "Low risk", n: checked.filter((l) => l.latest_recommendation!.risk_band === "low").length, color: RISK_COLOR.low },
    { label: "Medium risk", n: checked.filter((l) => l.latest_recommendation!.risk_band === "medium").length, color: RISK_COLOR.medium },
    { label: "High risk", n: checked.filter((l) => l.latest_recommendation!.risk_band === "high").length, color: RISK_COLOR.high },
    { label: "Not rated", n: checked.filter((l) => !l.latest_recommendation!.risk_band).length, color: RISK_COLOR.none },
  ];

  return (
    <>
      <PageHeader title="Prospect Dashboard" subtitle="New-customer pipeline across the five agents" />

      <div className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Stat icon={Users} label="Eligible to approach" value={eligible.length} sub={`of ${total} prospects`} href="/prospects?view=eligible" />
          <Stat icon={AlertTriangle} label="Underwriter review" value={underwriter.length} sub="Need an underwriter's look" tone="amber" href="/prospects?view=review" />
          <Stat icon={Flame} label="High-priority prospects" value={hot.length} sub="Top of the call list" tone="red" href="/prospects?view=high" />
          <Stat icon={ClipboardCheck} label="Awaiting approval" value={pending.length} sub="Need a staff decision" tone="green" href="/prospects?view=pending" />
        </div>

        <div className="grid gap-5 xl:grid-cols-[1.4fr_1fr_1fr]">
          <Panel title="Recommended next action">
            <ColumnChart rows={actions} />
          </Panel>
          <Panel title="Risk bands">
            <Donut parts={bands} centre="assessed" />
          </Panel>
          <Panel title="Lead priority">
            <Donut parts={priorities} centre="assessed" />
          </Panel>
        </div>
      </div>
    </>
  );
}
