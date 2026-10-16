"use client";

import { AlertTriangle, ClipboardCheck, Flame, Users } from "lucide-react";
import Link from "next/link";
import { RunAgentsButton } from "@/components/run-agents";
import { ColumnChart, CustomerCell, Donut, Empty, PageHeader, Panel, RISK_COLOR, RiskBadge, RowLink, Stat, Table, Td, ViewLink } from "@/components/kit";
import { ACTION_TONE, Badge, ErrorBox, Skeleton } from "@/components/ui";
import type { LeadOut } from "@/lib/api";
import { ACTION, LINE } from "@/lib/format";
import { isChecked, isEligible, needsUnderwriter, REC_STATUS, topProduct, useLeads } from "@/lib/leads";

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
  const underwriter = checked.filter((l) => needsUnderwriter(l) && isPending(l));
  const hot = checked.filter((l) => l.latest_recommendation!.priority === "high");

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
  const recent = [...checked].sort((a, b) => b.latest_recommendation!.created_at.localeCompare(a.latest_recommendation!.created_at)).slice(0, 6);

  return (
    <>
      <PageHeader title="Prospect Dashboard" subtitle="New-customer pipeline across the five agents">
        <RunAgentsButton />
      </PageHeader>

      <div className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Stat icon={Users} label="Eligible to approach" value={eligible.length} sub={`of ${total} prospects`} />
          <Stat icon={AlertTriangle} label="Underwriter review" value={underwriter.length} sub="Waiting for an underwriter" tone="amber" />
          <Stat icon={Flame} label="High-priority prospects" value={hot.length} sub="Top of the call list" tone="red" />
          <Stat icon={ClipboardCheck} label="Awaiting approval" value={pending.length} sub="Need a staff decision" tone="green" />
        </div>

        <div className="grid gap-5 xl:grid-cols-[1.6fr_1fr]">
          <Panel title="Recommended next action">
            <ColumnChart rows={actions} />
          </Panel>
          <Panel title="Risk bands">
            <Donut parts={bands} centre="assessed" />
          </Panel>
        </div>

        <Panel
          title="Recent recommendations"
          pad={false}
          action={
            <Link href="/priorities" className="text-sm font-semibold text-brand hover:underline">
              View all
            </Link>
          }
        >
          {recent.length === 0 ? (
            <Empty>No AI checks yet. Open Prospect Discovery and run the agents.</Empty>
          ) : (
            <Table head={["Customer", "Best product", "Risk", "Next action", "Status", ""]}>
              {recent.map((l) => {
                const r = l.latest_recommendation!;
                const st = REC_STATUS[r.status];
                return (
                  <RowLink key={l.id} href={`/customers/${l.id}?from=dashboard#summary`}>
                    <CustomerCell lead={l} sub={LINE[l.product_line ?? ""]} href={`/customers/${l.id}?from=dashboard#summary`} />
                    <Td>{topProduct(l) ?? <span className="text-xs text-muted-ink">Not matched</span>}</Td>
                    <Td>
                      <RiskBadge band={r.risk_band} />
                    </Td>
                    <Td>
                      <Badge tone={ACTION_TONE[r.action] ?? "gray"}>{ACTION[r.action] ?? r.action}</Badge>
                    </Td>
                    <Td>{st && <Badge tone={st.tone}>{st.label}</Badge>}</Td>
                    <Td>
                      <ViewLink href={`/customers/${l.id}?from=dashboard#summary`} />
                    </Td>
                  </RowLink>
                );
              })}
            </Table>
          )}
        </Panel>
      </div>
    </>
  );
}
