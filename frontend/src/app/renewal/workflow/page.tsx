"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type WorkflowOut } from "@/renewal/lib/api";
import { stamp } from "@/renewal/lib/format";
import { Badge, Card, Empty, ErrorNote, Loading, PageHeader, Pagination, STATUS_TONE, Table, Tabs, Td, RowLink } from "@/renewal/components/kit";

const LIMIT = 10;

type Filter = "" | "awaiting_approval" | "scheduled" | "sent" | "task_created" | "rejected" | "failed";

export default function WorkflowPage() {
  const [status, setStatus] = useState<Filter>("");
  const [offset, setOffset] = useState(0);
  const q = useQuery({
    queryKey: ["overview", "workflow", status],
    queryFn: () => api<WorkflowOut>("/overview/workflow", { query: { status, limit: 200 } }),
    refetchInterval: 5000,
  });
  const d = q.data;
  return (
    <>
      <PageHeader
        title="Workflow & Follow-ups"
        subtitle="Automate reminders, document requests and updates"
      />
      {q.error && <ErrorNote error={q.error} />}
      {!d ? (
        !q.error && <Loading />
      ) : (
        <div className="space-y-5">

          <Card pad={false}>
            <div className="border-b border-rule p-4">
              <Tabs<Filter>
                value={status}
                onChange={(v) => {
                  setStatus(v);
                  setOffset(0);
                }}
                options={[
                  { value: "", label: "All" },
                  { value: "awaiting_approval", label: "Awaiting approval" },
                  { value: "scheduled", label: "Scheduled" },
                  { value: "sent", label: "Sent" },
                  { value: "task_created", label: "Tasks" },
                  { value: "rejected", label: "Rejected" },
                ]}
              />
            </div>
            {d.items.length === 0 ? (
              <Empty>No follow-ups here yet. Run the agents from the Dashboard to create them.</Empty>
            ) : (
              <Table head={["Customer", "Workflow", "Channel", "Status", "Next Step", "Updated", ""]}>
                {d.items.slice(offset, offset + LIMIT).map((i) => (
                  <RowLink key={i.rec_id} href={`/renewal/customers/${i.policy_id}?from=workflow${i.status === "awaiting_approval" ? "#message" : "#history"}`}>
                    <Td>
                      <Link href={`/renewal/customers/${i.policy_id}?from=workflow${i.status === "awaiting_approval" ? "#message" : "#history"}`} className="font-semibold text-ink hover:text-brand">
                        {i.customer_name}
                      </Link>
                      <span className="block text-xs font-normal text-muted-ink">{i.policy_number}</span>
                    </Td>
                    <Td>
                      {i.workflow}
                      {i.link && <span className="block text-xs text-muted-ink">+ {i.link.label.toLowerCase()} link</span>}
                    </Td>
                    <Td>{i.channel}</Td>
                    <Td>
                      <Badge tone={STATUS_TONE[i.status] ?? "neutral"}>{i.status_label}</Badge>
                    </Td>
                    <Td className="text-brand">{i.next_step}</Td>
                    <Td className="text-xs whitespace-nowrap text-muted-ink">{stamp(i.updated_at)}</Td>
                    <Td>
                      <Link
                        href={`/renewal/customers/${i.policy_id}?from=workflow${i.status === "awaiting_approval" ? "#message" : "#history"}`}
                        className="font-semibold text-brand hover:underline"
                      >
                        {i.status === "awaiting_approval" ? "Review" : "View"}
                      </Link>
                    </Td>
                  </RowLink>
                ))}
              </Table>
            )}
            {d.items.length > LIMIT && (
              <Pagination total={d.items.length} limit={LIMIT} offset={offset} onChange={setOffset} />
            )}
          </Card>
        </div>
      )}
    </>
  );
}
