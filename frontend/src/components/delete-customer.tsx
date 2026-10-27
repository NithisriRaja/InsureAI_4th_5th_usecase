"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { cx } from "@/components/ui";

/** A bin icon that deletes a customer and all their AI results, after asking to confirm. */
export function DeleteCustomer({ id, name, onDeleted, className }: { id: string; name?: string | null; onDeleted?: () => void; className?: string }) {
  const qc = useQueryClient();
  const del = useMutation({
    mutationFn: () => api<void>(`/leads/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.removeQueries({ queryKey: ["lead", id] });
      onDeleted?.();
    },
    onError: (e) => window.alert(e instanceof Error ? e.message : "Could not delete this customer."),
    onSettled: () => qc.invalidateQueries(),
  });
  const label = `Delete ${name || "this customer"}`;
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      disabled={del.isPending}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        if (window.confirm(`Delete ${name || "this customer"} and all their AI results?\n\nThis can't be undone.`)) del.mutate();
      }}
      className={cx("grid size-8 place-items-center rounded-lg text-muted-ink transition-colors hover:bg-bad-soft hover:text-bad focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-bad/40 disabled:opacity-50", className)}
    >
      <Trash2 className="size-4" aria-hidden />
    </button>
  );
}
