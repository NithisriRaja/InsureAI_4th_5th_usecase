"use client";

import { useState } from "react";
import { CustomerCell, Empty, PageHeader, Pagination, RowLink, Table, Tabs, Td, ViewLink } from "@/components/kit";
import { ACTION_TONE, Badge, Card, ErrorBox, Skeleton } from "@/components/ui";
import type { LeadOut } from "@/lib/api";
import { ACTION, LINE, TEAM } from "@/lib/format";
import { contactRoute, isChecked, PRIORITY, REC_STATUS, useLeads } from "@/lib/leads";

type View = "pending" | "approved" | "rejected" | "all";
const LIMIT = 10;
const ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };

function inView(l: LeadOut, v: View) {
  const s = l.latest_recommendation!.status;
  if (v === "pending") return s === "pending_approval";
  if (v === "approved") return s === "approved" || s === "approved_with_edits";
  if (v === "rejected") return s === "rejected";
  return true;
}

export default function EngagementPage() {
  const q = useLeads();
  const [view, setView] = useState<View>("pending");
  const [offset, setOffset] = useState(0);
  if (q.isError) return <ErrorBox error={q.error} />;
  if (q.isPending) return <Skeleton className="h-96" />;

  const leads = q.data.items.filter(isChecked);
  const rows = leads.filter((l) => inView(l, view)).sort((a, b) => (ORDER[a.latest_recommendation!.priority] ?? 3) - (ORDER[b.latest_recommendation!.priority] ?? 3));
  const count = (v: View) => leads.filter((l) => inView(l, v)).length;

  return (
    <>
      <PageHeader title="Sales Engagement" subtitle="Next best action for each prospect. Nothing is sent until a person approves it." />
      <Card className="p-0">
        <div className="border-b border-rule p-4">
          <Tabs<View>
            value={view}
            onChange={(v) => {
              setView(v);
              setOffset(0);
            }}
            options={[
              { value: "pending", label: "Awaiting approval", count: count("pending") },
              { value: "approved", label: "Approved", count: count("approved") },
              { value: "rejected", label: "Rejected", count: count("rejected") },
              { value: "all", label: "All", count: leads.length },
            ]}
          />
        </div>
        {rows.length === 0 ? (
          <Empty>Nothing here.</Empty>
        ) : (
          <>
            <Table head={["Customer", "Next action", "Contact via", "Priority", "Who approves", "Status", ""]}>
              {rows.slice(offset, offset + LIMIT).map((l) => {
                const r = l.latest_recommendation!;
                const p = PRIORITY[r.priority];
                const st = REC_STATUS[r.status];
                return (
                  <RowLink key={l.id} href={`/customers/${l.id}?from=engagement#decision`}>
                    <CustomerCell lead={l} sub={LINE[l.product_line ?? ""]} href={`/customers/${l.id}?from=engagement#decision`} />
                    <Td>
                      <Badge tone={ACTION_TONE[r.action] ?? "gray"}>{ACTION[r.action] ?? r.action}</Badge>
                    </Td>
                    <Td>{contactRoute(l)}</Td>
                    <Td>{p && <Badge tone={p.tone}>{p.label}</Badge>}</Td>
                    <Td>{TEAM[r.queue] ?? r.queue}</Td>
                    <Td>{st && <Badge tone={st.tone}>{st.label}</Badge>}</Td>
                    <Td>
                      <ViewLink href={`/customers/${l.id}?from=engagement#decision`}>{r.status === "pending_approval" ? "Review" : "View"}</ViewLink>
                    </Td>
                  </RowLink>
                );
              })}
            </Table>
            <Pagination total={rows.length} limit={LIMIT} offset={offset} onChange={setOffset} />
          </>
        )}
      </Card>
    </>
  );
}
