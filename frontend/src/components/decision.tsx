"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, CheckCircle2, Gavel, Pencil, X, XCircle } from "lucide-react";
import { type ReactNode, useState } from "react";
import { QUEUE_ROLES, ROLES, useUser } from "@/components/session";
import { Badge, Button, Card, CardTitle, cx } from "@/components/ui";
import { api, ApiError, type Approval, type Justification, type RecDetail } from "@/lib/api";
import { ACTION, date } from "@/lib/format";

// Actions a reviewer may switch between (mirrors services/approvals.EDITABLE_ACTIONS).
const EDITABLE = ["contact_and_quote", "nurture", "refer_to_underwriter"];
const TEAM: Record<string, string> = { sales: "Sales & marketing", adviser: "Adviser", underwriting: "Underwriting" };
const DECIDED: Record<string, { label: string; tone: "green" | "red" | "gray" }> = {
  approved: { label: "Approved", tone: "green" },
  approved_with_edits: { label: "Approved with a change", tone: "green" },
  rejected: { label: "Rejected", tone: "red" },
  superseded: { label: "Replaced by a newer AI check", tone: "gray" },
  expired: { label: "Expired: re-run the AI", tone: "gray" },
};

function Wrap({ bare, children }: { bare?: boolean; children: ReactNode }) {
  return bare ? <div>{children}</div> : <Card>{children}</Card>;
}

export function DecisionPanel({ rec, bare }: { rec: RecDetail; bare?: boolean }) {
  const qc = useQueryClient();
  const { user } = useUser();
  const [mode, setMode] = useState<"idle" | "edit" | "reject">("idle");
  const [action, setAction] = useState(rec.action);
  const [reason, setReason] = useState("");
  const [ticked, setTicked] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const checks = ((rec.justification ?? {}) as Justification).approver_items ?? [];
  const approval = rec.approval as Approval | null | undefined;
  const allowed = QUEUE_ROLES[rec.queue] ?? ["admin"];
  const mayDecide = !!user && allowed.includes(user.role);
  const allTicked = ticked.size === checks.length;
  const canEdit = EDITABLE.includes(rec.action) && rec.action !== "refer_to_underwriter";

  const decide = useMutation({
    mutationFn: (kind: "approve" | "edit" | "reject") =>
      api(`/approvals/${rec.id}/${kind}`, {
        method: "POST",
        body: {
          expected_version: rec.version,
          ...(kind === "reject" ? { reason } : {}),
          ...(kind === "edit" ? { edits: { action }, reason: reason || undefined } : {}),
        },
      }),
    onSuccess: () => {
      setMode("idle");
      setError(null);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === "stale") setError(`${e.message} Re-run the AI for a fresh suggestion.`);
      else if (e instanceof ApiError && e.status === 409) setError(`${e.message} The page has been refreshed.`);
      else setError(e instanceof Error ? e.message : "Could not save the decision.");
    },
    onSettled: () => qc.invalidateQueries(),
  });

  if (rec.status !== "pending_approval") {
    const d = DECIDED[rec.status] ?? { label: rec.status, tone: "gray" as const };
    return (
      <Wrap bare={bare}>
        <CardTitle icon={<Gavel className="size-4 text-brand" />}>Decision</CardTitle>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Badge tone={d.tone}>
            {d.tone === "red" ? <XCircle className="size-3" /> : <CheckCircle2 className="size-3" />} {d.label}
          </Badge>
          {approval && (
            <span className="text-ink-2">
              by <span className="font-medium">{approval.actor}</span> ({approval.role}) on {date(approval.at)}
            </span>
          )}
        </div>
        {approval?.edits?.action ? (
          <p className="mt-2 text-sm text-ink-2">
            Changed the action to <span className="font-medium">{ACTION[String(approval.edits.action)]}</span>.
          </p>
        ) : null}
        {approval?.reason && <p className="mt-2 rounded-lg bg-soft p-3 text-sm text-ink-2">&ldquo;{approval.reason}&rdquo;</p>}
      </Wrap>
    );
  }

  return (
    <Wrap bare={bare}>
      <CardTitle
        icon={<Gavel className="size-4 text-brand" />}
        hint={`${TEAM[rec.queue] ?? rec.queue} team decides · expires ${date(rec.expires_at)}`}
      >
        Your decision
      </CardTitle>

      {!user ? (
        <p className="text-sm text-muted">Connecting to the server…</p>
      ) : !mayDecide ? (
        <p className="text-sm text-muted">
          Signed in as {ROLES.find((r) => r.value === user.role)?.label}. Only the {TEAM[rec.queue] ?? rec.queue} team
          (or an admin) can decide this case.
        </p>
      ) : (
        <div className="space-y-4">
          {checks.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-medium text-muted">Confirm before approving</p>
              <ul className="space-y-1.5">
                {checks.map((c, i) => (
                  <li key={i}>
                    <label className="flex cursor-pointer gap-2 text-sm">
                      <input
                        type="checkbox"
                        className="mt-1 accent-[var(--brand)]"
                        checked={ticked.has(i)}
                        onChange={() => {
                          const next = new Set(ticked);
                          if (next.has(i)) next.delete(i);
                          else next.add(i);
                          setTicked(next);
                        }}
                      />
                      <span>
                        <span className="font-medium text-ink">{c.title}</span>
                        {c.detail && <span className="text-ink-2"> · {c.detail}</span>}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {mode === "edit" && (
            <div className="space-y-2 rounded-lg bg-soft p-3">
              <p className="text-xs font-medium text-muted">Change the next step, then approve</p>
              <div className="flex flex-wrap gap-2">
                {EDITABLE.filter((a) => a !== rec.action).map((a) => (
                  <button
                    key={a}
                    onClick={() => setAction(a)}
                    className={cx(
                      "rounded-lg border px-3 py-1.5 text-sm",
                      action === a ? "border-brand bg-brand-soft text-brand" : "border-line bg-card text-ink-2",
                    )}
                  >
                    {ACTION[a]}
                  </button>
                ))}
              </div>
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Why (optional)"
                className="w-full rounded-lg border border-line bg-card px-2.5 py-1.5 text-sm outline-none focus:border-brand"
              />
            </div>
          )}
          {mode === "reject" && (
            <div className="space-y-2 rounded-lg bg-soft p-3">
              <p className="text-xs font-medium text-muted">Why are you rejecting it? (required)</p>
              <div className="flex flex-wrap gap-1.5">
                {["Customer not interested", "Already insured elsewhere", "Facts are wrong", "Wrong product"].map((r) => (
                  <button key={r} onClick={() => setReason(r)} className="rounded-full border border-line bg-card px-2.5 py-1 text-xs">
                    {r}
                  </button>
                ))}
              </div>
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Reason"
                className="w-full rounded-lg border border-line bg-card px-2.5 py-1.5 text-sm outline-none focus:border-brand"
              />
            </div>
          )}

          {error && <p className="text-sm text-bad">{error}</p>}

          <div className="flex flex-wrap gap-2">
            {mode === "idle" && (
              <>
                <Button busy={decide.isPending} disabled={!allTicked} onClick={() => decide.mutate("approve")}>
                  <Check className="size-4" /> Approve
                </Button>
                {canEdit && (
                  <Button variant="ghost" onClick={() => setMode("edit")}>
                    <Pencil className="size-4" /> Change action
                  </Button>
                )}
                <Button variant="ghost" onClick={() => setMode("reject")}>
                  <X className="size-4" /> Reject
                </Button>
              </>
            )}
            {mode === "edit" && (
              <>
                <Button
                  busy={decide.isPending}
                  disabled={!allTicked || action === rec.action}
                  onClick={() => decide.mutate("edit")}
                >
                  <Check className="size-4" /> Approve as {ACTION[action] ?? action}
                </Button>
                <Button variant="ghost" onClick={() => setMode("idle")}>
                  Cancel
                </Button>
              </>
            )}
            {mode === "reject" && (
              <>
                <Button busy={decide.isPending} disabled={!reason.trim()} onClick={() => decide.mutate("reject")}>
                  <X className="size-4" /> Reject
                </Button>
                <Button variant="ghost" onClick={() => setMode("idle")}>
                  Cancel
                </Button>
              </>
            )}
          </div>
          {!allTicked && mode !== "reject" && <p className="text-xs text-muted">Tick every check to approve.</p>}
        </div>
      )}
    </Wrap>
  );
}
