"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, RotateCw } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui";
import { api, type BatchOut } from "@/lib/api";
import { useRunAll } from "@/lib/hooks";
import { useLeads } from "@/lib/leads";

/** Run the agents on every prospect that needs it: new ones first, otherwise re-check the open
 *  suggestions. Prospects a person already approved or rejected are never re-run (backend rule). */
export function RunAgentsButton() {
  const qc = useQueryClient();
  const leads = useLeads();
  const runAll = useRunAll();
  const [batchId, setBatchId] = useState<string | null>(null);
  const batch = useQuery({
    queryKey: ["batch", batchId],
    queryFn: async () => {
      const b = await api<BatchOut>(`/batches/${batchId}`);
      if (b.done) {
        setBatchId(null);
        qc.invalidateQueries();
      }
      return b;
    },
    enabled: !!batchId,
    refetchInterval: 2_000,
  });

  const items = leads.data?.items ?? [];
  const fresh = items.filter((l) => ["new", "failed"].includes(l.status)).length;
  const open = items.filter((l) => l.status === "recommended").length;

  if (batchId) {
    const b = batch.data;
    const finished = b ? b.total - (b.counts.queued ?? 0) - (b.counts.running ?? 0) : 0;
    return (
      <Button busy>
        Agents working… {b ? `${finished} / ${b.total}` : ""}
      </Button>
    );
  }

  const start = (scope: "unchecked" | "all") => runAll.mutate(scope, { onSuccess: (b) => setBatchId(b.id) });

  if (fresh > 0)
    return (
      <Button busy={runAll.isPending} onClick={() => start("unchecked")}>
        <Play className="size-4" /> Run agents on {fresh} new
      </Button>
    );

  return (
    <Button
      busy={runAll.isPending}
      disabled={open === 0}
      title={open === 0 ? "Every prospect has been decided by staff" : undefined}
      onClick={() => start("all")}
    >
      <RotateCw className="size-4" /> Run agents again
    </Button>
  );
}
