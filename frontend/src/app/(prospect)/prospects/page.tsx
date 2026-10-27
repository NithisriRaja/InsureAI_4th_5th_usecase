"use client";

import { Play } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { DeleteCustomer } from "@/components/delete-customer";
import { CustomerCell, Empty, PageHeader, Pagination, RiskBadge, RowLink, SearchBox, Table, Tabs, Td, ViewLink } from "@/components/kit";
import { Badge, Button, Card, ErrorBox, Skeleton } from "@/components/ui";
import { ACTIVE_RUN } from "@/lib/api";
import { LINE, money } from "@/lib/format";
import { useRunLead } from "@/lib/hooks";
import { eligibility, PRIORITY, useLeads } from "@/lib/leads";

type View = "all" | "eligible" | "review" | "high" | "pending";
const VIEWS: View[] = ["all", "eligible", "review", "high", "pending"];
const LIMIT = 10;

function FilterSelect({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: string[][] }) {
  return (
    <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} className="h-9 rounded-lg border border-rule-2 bg-card px-2.5 text-sm text-ink focus:border-brand focus:outline-none">
      <option value="">{label}: all</option>
      {options.map(([k, t]) => (
        <option key={k} value={k}>
          {t}
        </option>
      ))}
    </select>
  );
}

export default function ProspectsPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <Prospects />
    </Suspense>
  );
}

function Prospects() {
  const q = useLeads();
  const runOne = useRunLead();
  const [search, setSearch] = useState("");
  const wanted = useSearchParams().get("view") as View | null;
  const [view, setView] = useState<View>(wanted && VIEWS.includes(wanted) ? wanted : "all");
  const [risk, setRisk] = useState("");
  const [priority, setPriority] = useState("");
  const [offset, setOffset] = useState(0);

  if (q.isError) return <ErrorBox error={q.error} />;
  if (q.isPending) return <Skeleton className="h-96" />;

  const all = q.data.items;
  const term = search.trim().toLowerCase();
  const isHigh = (l: (typeof all)[number]) => l.latest_recommendation?.priority === "high";
  const inView = (l: (typeof all)[number], k: View) => (k === "all" ? true : k === "high" ? isHigh(l) : k === "pending" ? l.latest_recommendation?.status === "pending_approval" : eligibility(l).key === k);
  const count = (k: View) => all.filter((l) => inView(l, k)).length;
  const rows = all.filter((l) => inView(l, view) && (!risk || (l.latest_recommendation?.risk_band ?? "none") === risk) && (!priority || l.latest_recommendation?.priority === priority) && (!term || `${l.name} ${l.external_ref ?? ""}`.toLowerCase().includes(term)));
  const go = (fn: () => void) => {
    fn();
    setOffset(0);
  };

  return (
    <>
      <PageHeader title="Prospect Discovery" subtitle="Who we may approach, using approved data and customer consent" />

      <Card className="p-0">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rule p-4">
          <Tabs<View>
            value={view}
            onChange={(v) => go(() => setView(v))}
            options={[
              { value: "all", label: "All", count: all.length },
              { value: "eligible", label: "Eligible", count: count("eligible") },
              { value: "review", label: "Underwriter review", count: count("review") },
              { value: "high", label: "High priority", count: count("high") },
              { value: "pending", label: "Awaiting approval", count: count("pending") },
            ]}
          />
          <div className="flex flex-wrap items-center gap-2">
            <FilterSelect label="Risk" value={risk} onChange={(v) => go(() => setRisk(v))} options={[["low", "Low risk"], ["medium", "Medium risk"], ["high", "High risk"], ["none", "Not rated"]]} />
            <FilterSelect label="Priority" value={priority} onChange={(v) => go(() => setPriority(v))} options={Object.entries(PRIORITY).map(([k, p]) => [k, `${p.label} priority`])} />
            <SearchBox value={search} onChange={(v) => go(() => setSearch(v))} placeholder="Name or reference" />
          </div>
        </div>

        {rows.length === 0 ? (
          <Empty>No prospects in this view.</Empty>
        ) : (
          <>
            <Table head={["Customer", "Interested in", "Cover requested", "Risk", "Priority", "Status", ""]}>
              {rows.slice(offset, offset + LIMIT).map((l) => {
                const e = eligibility(l);
                const busy = ACTIVE_RUN.includes(l.latest_run?.status ?? "") || (runOne.isPending && runOne.variables === l.id);
                return (
                  <RowLink key={l.id} href={`/customers/${l.id}?from=prospects`}>
                    <CustomerCell lead={l} sub={l.external_ref} href={`/customers/${l.id}?from=prospects`} />
                    <Td>{LINE[l.product_line ?? ""] ?? "—"}</Td>
                    <Td className="whitespace-nowrap">{money(l.sum_insured)}</Td>
                    <Td>{l.latest_recommendation?.risk_band ? <RiskBadge band={l.latest_recommendation.risk_band} /> : "—"}</Td>
                    <Td>{PRIORITY[l.latest_recommendation?.priority ?? ""] ? <Badge tone={PRIORITY[l.latest_recommendation!.priority].tone}>{PRIORITY[l.latest_recommendation!.priority].label}</Badge> : "—"}</Td>
                    <Td>{busy ? <Badge tone="blue">Agents working…</Badge> : <Badge tone={e.tone}>{e.label}</Badge>}</Td>
                    <Td className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        {e.key === "none" && !busy ? (
                          <Button variant="ghost" onClick={() => runOne.mutate(l.id)}>
                            <Play className="size-3.5" /> Run
                          </Button>
                        ) : (
                          <ViewLink href={`/customers/${l.id}?from=prospects`} />
                        )}
                        <DeleteCustomer id={l.id} name={l.name} />
                      </div>
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
