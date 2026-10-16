"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type BatchOut, type RunOut } from "./api";

/** Queue an AI check for one lead (or all unchecked ones), then refresh lists. */
export function useRunLead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (leadId: string) => api<RunOut>(`/leads/${leadId}/runs`, { method: "POST" }),
    onSettled: () => qc.invalidateQueries(),
  });
}

/** Queue the AI for every matching customer. "all" also re-checks open suggestions; customers
 *  already approved or rejected are never re-run (by the backend). */
export function useRunAll() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (scope: "unchecked" | "all") => api<BatchOut>("/leads/runs", { method: "POST", query: { scope } }),
    onSettled: () => qc.invalidateQueries(),
  });
}
