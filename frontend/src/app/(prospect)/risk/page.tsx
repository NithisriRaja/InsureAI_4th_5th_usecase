"use client";

import { useState } from "react";
import { CustomerCell, Donut, Empty, Gauge, PageHeader, Pagination, Panel, RISK_COLOR, RiskBadge, RowLink, Table, Tabs, Td, ViewLink } from "@/components/kit";
import { Badge, ErrorBox, Skeleton } from "@/components/ui";
import { LINE } from "@/lib/format";
import { isChecked, needsUnderwriter, useLeads } from "@/lib/leads";

type View = "all" | "uw" | "ok";
const LIMIT = 10;

export default function RiskPage() {
  const q = useLeads();
  const [view, setView] = useState<View>("all");
  const [offset, setOffset] = useState(0);

  if (q.isError) return <ErrorBox error={q.error} />;
  if (q.isPending) return <Skeleton className="h-96" />;

  const leads = q.data.items.filter(isChecked);
  const referred = leads.filter(needsUnderwriter);
  const band = (b: string | null) => leads.filter((l) => (l.latest_recommendation!.risk_band ?? null) === b).length;
  const rows = leads.filter((l) => view === "all" || (view === "uw" ? needsUnderwriter(l) : !needsUnderwriter(l)));
  const waiting = referred.filter((l) => l.latest_recommendation!.status === "pending_approval").length;

  return (
    <>
      <PageHeader title="Risk Assessment" subtitle="Key risk level for each prospect, and the cases an underwriter must review" />

      <div className="space-y-5">
        <div className="grid gap-5 lg:grid-cols-2">
          <Panel title="Risk bands">
            <Donut
              centre="assessed"
              parts={[
                { label: "Low risk", n: band("low"), color: RISK_COLOR.low },
                { label: "Medium risk", n: band("medium"), color: RISK_COLOR.medium },
                { label: "High risk", n: band("high"), color: RISK_COLOR.high },
                { label: "Not rated", n: band(null), color: RISK_COLOR.none },
              ]}
            />
          </Panel>
          <Panel title="Underwriter review">
            <div className="flex flex-col items-center">
              <Gauge value={referred.length} max={leads.length} label="need an underwriter" />
              <p className="mt-2 text-sm text-muted-ink">
                <b className="text-ink">{waiting}</b> waiting · <b className="text-ink">{referred.length - waiting}</b> decided · of {leads.length} assessed
              </p>
            </div>
          </Panel>
        </div>

        <Panel title="Assessed prospects" pad={false}>
          <div className="border-b border-rule px-4 pb-4">
            <Tabs<View>
              value={view}
              onChange={(v) => {
                setView(v);
                setOffset(0);
              }}
              options={[
                { value: "all", label: "All", count: leads.length },
                { value: "uw", label: "Needs underwriter", count: referred.length },
                { value: "ok", label: "No review needed", count: leads.length - referred.length },
              ]}
            />
          </div>
          {rows.length === 0 ? (
            <Empty>No assessed prospects here. Run the agents from Prospect Discovery.</Empty>
          ) : (
            <>
              <Table head={["Customer", "Interested in", "Risk level", "Risk score", "Underwriter review", ""]}>
                {rows.slice(offset, offset + LIMIT).map((l) => {
                  const r = l.latest_recommendation!;
                  return (
                    <RowLink key={l.id} href={`/customers/${l.id}?from=risk#risk`}>
                      <CustomerCell lead={l} href={`/customers/${l.id}?from=risk#risk`} />
                      <Td>{LINE[l.product_line ?? ""] ?? "—"}</Td>
                      <Td>
                        <RiskBadge band={r.risk_band} />
                      </Td>
                      <Td className="font-semibold text-ink tabular-nums">{typeof r.risk_score === "number" ? `${Math.round(r.risk_score * 100)} / 100` : "—"}</Td>
                      <Td>{needsUnderwriter(l) ? <Badge tone="amber">Required</Badge> : <Badge tone="green">Not needed</Badge>}</Td>
                      <Td>
                        <ViewLink href={`/customers/${l.id}?from=risk#risk`} />
                      </Td>
                    </RowLink>
                  );
                })}
              </Table>
              <Pagination total={rows.length} limit={LIMIT} offset={offset} onChange={setOffset} />
            </>
          )}
        </Panel>
      </div>
    </>
  );
}
