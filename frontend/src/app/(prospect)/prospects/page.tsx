"use client";

import { Play } from "lucide-react";
import { useState } from "react";
import { RunAgentsButton } from "@/components/run-agents";
import { CustomerCell, Empty, PageHeader, Pagination, RowLink, SearchBox, Table, Tabs, Td, ViewLink } from "@/components/kit";
import { Badge, Button, Card, ErrorBox, Skeleton } from "@/components/ui";
import { ACTIVE_RUN } from "@/lib/api";
import { LINE, money, OWNER } from "@/lib/format";
import { useRunLead } from "@/lib/hooks";
import { eligibility, useLeads } from "@/lib/leads";

type View = "all" | "eligible" | "review" | "blocked" | "none";
const LIMIT = 10;

export default function ProspectsPage() {
  const q = useLeads();
  const runOne = useRunLead();
  const [search, setSearch] = useState("");
  const [view, setView] = useState<View>("all");
  const [offset, setOffset] = useState(0);

  if (q.isError) return <ErrorBox error={q.error} />;
  if (q.isPending) return <Skeleton className="h-96" />;

  const all = q.data.items;
  const term = search.trim().toLowerCase();
  const count = (k: View) => all.filter((l) => eligibility(l).key === k).length;
  const rows = all.filter((l) => (view === "all" || eligibility(l).key === view) && (!term || `${l.name} ${l.external_ref ?? ""}`.toLowerCase().includes(term)));
  const unchecked = count("none");
  const go = (fn: () => void) => {
    fn();
    setOffset(0);
  };

  return (
    <>
      <PageHeader title="Prospect Discovery" subtitle="Who we may approach, using approved data and customer consent">
        <RunAgentsButton />
      </PageHeader>

      <Card className="p-0">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rule p-4">
          <Tabs<View>
            value={view}
            onChange={(v) => go(() => setView(v))}
            options={[
              { value: "all", label: "All", count: all.length },
              { value: "eligible", label: "Eligible", count: count("eligible") },
              { value: "review", label: "Underwriter review", count: count("review") },
              { value: "blocked", label: "Can't approach", count: count("blocked") },
              { value: "none", label: "Not assessed", count: unchecked },
            ]}
          />
          <SearchBox value={search} onChange={(v) => go(() => setSearch(v))} placeholder="Name or reference" />
        </div>

        {rows.length === 0 ? (
          <Empty>No prospects in this view.</Empty>
        ) : (
          <>
            <Table head={["Customer", "Interested in", "Cover requested", "Handled by", "Status", ""]}>
              {rows.slice(offset, offset + LIMIT).map((l) => {
                const e = eligibility(l);
                const busy = ACTIVE_RUN.includes(l.latest_run?.status ?? "") || (runOne.isPending && runOne.variables === l.id);
                return (
                  <RowLink key={l.id} href={`/customers/${l.id}?from=prospects`}>
                    <CustomerCell lead={l} sub={l.external_ref} href={`/customers/${l.id}?from=prospects`} />
                    <Td>{LINE[l.product_line ?? ""] ?? "—"}</Td>
                    <Td className="whitespace-nowrap">{money(l.sum_insured)}</Td>
                    <Td>{OWNER[l.channel_owner] ?? l.channel_owner}</Td>
                    <Td>{busy ? <Badge tone="blue">Agents working…</Badge> : <Badge tone={e.tone}>{e.label}</Badge>}</Td>
                    <Td className="text-right">
                      {e.key === "none" && !busy ? (
                        <Button variant="ghost" onClick={() => runOne.mutate(l.id)}>
                          <Play className="size-3.5" /> Run
                        </Button>
                      ) : (
                        <ViewLink href={`/customers/${l.id}?from=prospects`} />
                      )}
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
