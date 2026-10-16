"use client";

import { useState } from "react";
import { CustomerCell, Empty, PageHeader, Pagination, RowLink, Table, Tabs, Td, ViewLink } from "@/components/kit";
import { ACTION_TONE, Badge, Card, ErrorBox, Skeleton } from "@/components/ui";
import type { LeadOut } from "@/lib/api";
import { ACTION, LINE } from "@/lib/format";
import { isChecked, PRIORITY, reach, useLeads } from "@/lib/leads";

type View = "all" | "high" | "medium" | "low";
const LIMIT = 10;
const priority = (l: LeadOut) => l.latest_recommendation!.priority;

export default function PrioritiesPage() {
  const q = useLeads();
  const [view, setView] = useState<View>("all");
  const [offset, setOffset] = useState(0);
  if (q.isError) return <ErrorBox error={q.error} />;
  if (q.isPending) return <Skeleton className="h-96" />;

  // Ranked by the lead score (0-100); unscored cases go last.
  const ranked = q.data.items.filter(isChecked).sort((a, b) => (reach(b)?.score ?? -1) - (reach(a)?.score ?? -1));
  const n = (p: string) => ranked.filter((l) => priority(l) === p).length;
  const rows = ranked.filter((l) => view === "all" || priority(l) === view);

  return (
    <>
      <PageHeader title="Lead Prioritization" subtitle="Who to call first, ranked by lead score" />
      <Card className="p-0">
        <div className="border-b border-rule p-4">
          <Tabs<View>
            value={view}
            onChange={(v) => {
              setView(v);
              setOffset(0);
            }}
            options={[
              { value: "all", label: "All", count: ranked.length },
              { value: "high", label: "High", count: n("high") },
              { value: "medium", label: "Medium", count: n("medium") },
              { value: "low", label: "Low", count: n("low") },
            ]}
          />
        </div>
        {rows.length === 0 ? (
          <Empty>No assessed leads here. Run the agents from Prospect Discovery.</Empty>
        ) : (
          <>
            <Table head={["Rank", "Customer", "Interested in", "Lead score", "Priority", "Next action", ""]}>
              {rows.slice(offset, offset + LIMIT).map((l, i) => {
                const r = l.latest_recommendation!;
                const p = PRIORITY[r.priority];
                const score = reach(l)?.score;
                return (
                  <RowLink key={l.id} href={`/customers/${l.id}?from=priorities#summary`}>
                    <Td className="font-semibold text-ink">{offset + i + 1}</Td>
                    <CustomerCell lead={l} href={`/customers/${l.id}?from=priorities#summary`} />
                    <Td>{LINE[l.product_line ?? ""] ?? "—"}</Td>
                    <Td className="font-semibold text-ink tabular-nums">{typeof score === "number" ? `${score} / 100` : "—"}</Td>
                    <Td>{p && <Badge tone={p.tone}>{p.label}</Badge>}</Td>
                    <Td>
                      <Badge tone={ACTION_TONE[r.action] ?? "gray"}>{ACTION[r.action] ?? r.action}</Badge>
                    </Td>
                    <Td>
                      <ViewLink href={`/customers/${l.id}?from=priorities#summary`} />
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
