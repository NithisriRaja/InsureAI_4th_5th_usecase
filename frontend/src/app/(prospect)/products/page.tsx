"use client";

import { Building2, Car, HeartPulse, Home, type LucideIcon, PiggyBank, Shield, Sparkles, Umbrella, Users } from "lucide-react";
import { useState } from "react";
import { CustomerCell, Empty, PageHeader, Pagination, Panel, RowLink, Table, Tabs, Td, ViewLink } from "@/components/kit";
import { Badge, ErrorBox, Skeleton } from "@/components/ui";
import type { LeadOut } from "@/lib/api";
import { ACTION, LINE } from "@/lib/format";
import { isChecked, topProduct, useLeads } from "@/lib/leads";

type View = "all" | "matched" | "none";
const LIMIT = 10;
const matched = (l: LeadOut) => !!topProduct(l);
const ICON: Record<string, LucideIcon> = { motor: Car, medical: HeartPulse, home: Home, personal_accident: Umbrella, life: Shield, savings: PiggyBank, group: Building2, family: Users };

export default function ProductsPage() {
  const q = useLeads();
  const [view, setView] = useState<View>("all");
  const [offset, setOffset] = useState(0);

  if (q.isError) return <ErrorBox error={q.error} />;
  if (q.isPending) return <Skeleton className="h-96" />;

  const leads = q.data.items.filter(isChecked);
  const rows = leads.filter((l) => view === "all" || (view === "matched" ? matched(l) : !matched(l)));
  // Each recommended product with how many prospects it is the best fit for.
  const byProduct = new Map<string, { name: string; line: string; n: number }>();
  for (const l of leads) {
    const name = topProduct(l);
    if (!name) continue;
    const p = byProduct.get(name) ?? { name, line: l.product_line ?? "", n: 0 };
    p.n += 1;
    byProduct.set(name, p);
  }
  const top = [...byProduct.values()].sort((a, b) => b.n - a.n || a.name.localeCompare(b.name));

  return (
    <>
      <PageHeader title="Product Matching" subtitle="The best product for each prospect, within the eligibility rules" />

      <div className="space-y-5">
        {top.length > 0 && (
          <Panel title="Recommended products">
            <ul className="grid gap-x-10 sm:grid-cols-2 xl:grid-cols-3">
              {top.map((p) => {
                const Icon = ICON[p.line] ?? Shield;
                return (
                  <li key={p.name} className="flex items-center gap-3 border-b border-rule py-3">
                    <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand">
                      <Icon className="size-5" aria-hidden />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-semibold text-ink">{p.name}</span>
                      <span className="block text-xs text-muted-ink">{LINE[p.line] ?? p.line}</span>
                    </span>
                    <span className="shrink-0 rounded-full bg-ice-2 px-2.5 py-1 text-xs font-semibold whitespace-nowrap text-ink-2 tabular-nums">
                      {p.n} {p.n === 1 ? "prospect" : "prospects"}
                    </span>
                  </li>
                );
              })}
            </ul>
          </Panel>
        )}

        <Panel title="Matches by prospect" pad={false}>
          <div className="border-b border-rule px-4 pb-4">
            <Tabs<View>
              value={view}
              onChange={(v) => {
                setView(v);
                setOffset(0);
              }}
              options={[
                { value: "all", label: "All", count: leads.length },
                { value: "matched", label: "Matched", count: leads.filter(matched).length },
                { value: "none", label: "No match", count: leads.filter((l) => !matched(l)).length },
              ]}
            />
          </div>
          {rows.length === 0 ? (
            <Empty>No prospects here. Run the agents from Prospect Discovery.</Empty>
          ) : (
            <>
              <Table head={["Customer", "Interested in", "Best product", "Also suits", ""]}>
                {rows.slice(offset, offset + LIMIT).map((l) => {
                  const r = l.latest_recommendation!;
                  const best = topProduct(l);
                  return (
                    <RowLink key={l.id} href={`/customers/${l.id}?from=products#products`}>
                      <CustomerCell lead={l} href={`/customers/${l.id}?from=products#products`} />
                      <Td>{LINE[l.product_line ?? ""] ?? "—"}</Td>
                      <Td>
                        {best ? (
                          <Badge tone="brand">
                            <Sparkles className="size-3" aria-hidden /> {best}
                          </Badge>
                        ) : (
                          <span className="text-muted-ink">None · {ACTION[r.action] ?? r.action}</span>
                        )}
                      </Td>
                      <Td>{r.also_suits?.length ? r.also_suits.join(", ") : "—"}</Td>
                      <Td>
                        <ViewLink href={`/customers/${l.id}?from=products#products`} />
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
