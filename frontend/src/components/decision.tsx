"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, CheckCircle2, Gavel, Info, Pencil, X, XCircle } from "lucide-react";
import { type ReactNode, useState } from "react";
import { QUEUE_ROLES, ROLES, useUser } from "@/components/session";
import { Badge, Button, Card, CardTitle, cx } from "@/components/ui";
import { api, ApiError, type Approval, type Justification, type RecDetail, type Screened } from "@/lib/api";
import { ACTION, date } from "@/lib/format";

// Actions a reviewer may switch between (mirrors services/approvals.EDITABLE_ACTIONS).
const EDITABLE = ["contact_and_quote", "nurture", "refer_to_underwriter"];
const WHO: Record<string, string> = { sales: "the sales & marketing team", adviser: "the adviser", underwriting: "the underwriter" };
const DECIDED: Record<string, { label: string; tone: "green" | "red" | "gray" }> = {
  approved: { label: "Approved", tone: "green" },
  approved_with_edits: { label: "Approved with a change", tone: "green" },
  rejected: { label: "Rejected", tone: "red" },
  superseded: { label: "Replaced by a newer AI check", tone: "gray" },
  expired: { label: "Expired: re-run the AI", tone: "gray" },
};

/** What the approver must tick: real concerns only. Standard notes ("this logs a do-not-contact",
 *  "goes via the broker") are shown as information. */
type Item = { kind?: string; title: string; detail?: string };
const mustTick = (c: Item) => c.kind === "flag" || c.kind === "rule" || (c.kind === "confidence" && /low/i.test(c.title));

const REASONS = ["Customer not interested", "Already insured elsewhere", "Facts are wrong", "Wrong product"];

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

  const items = ((((rec.justification ?? {}) as Justification).approver_items ?? []) as Item[]).filter((c) => !/document/i.test(c.title));
  const must = items.filter(mustTick);
  const notes = items.filter((c) => !mustTick(c));
  const approval = rec.approval as Approval | null | undefined;
  const allowed = QUEUE_ROLES[rec.queue] ?? ["admin"];
  const mayDecide = !!user && allowed.includes(user.role);
  const allTicked = ticked.size === must.length;
  const canEdit = EDITABLE.includes(rec.action) && rec.action !== "refer_to_underwriter";
  const best = ((rec.product_screening ?? []) as Screened[]).find((x) => x.requested_line && x.ai_status === "recommended")?.name;
  const who = WHO[rec.queue] ?? rec.queue;

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

  // ---- already decided: a record of who did what
  if (rec.status !== "pending_approval") {
    const d = DECIDED[rec.status] ?? { label: rec.status, tone: "gray" as const };
    return (
      <Wrap bare={bare}>
        <CardTitle icon={<Gavel className="size-4 text-brand" />}>Decision</CardTitle>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={d.tone}>
            {d.tone === "red" ? <XCircle className="size-3" /> : <CheckCircle2 className="size-3" />} {d.label}
          </Badge>
        </div>
        {approval && (
          <p className="mt-3 text-sm text-ink-2">
            By <span className="font-semibold text-ink">{approval.actor}</span>, {approval.role}, on {date(approval.at)}
          </p>
        )}
        {approval?.edits?.action ? (
          <p className="mt-2 text-sm text-ink-2">
            Next step changed to <span className="font-semibold text-ink">{ACTION[String(approval.edits.action)]}</span>.
          </p>
        ) : null}
        {approval?.reason && <p className="mt-3 rounded-xl bg-ice p-3 text-sm text-ink-2">&ldquo;{approval.reason}&rdquo;</p>}
      </Wrap>
    );
  }

  // ---- waiting for a person
  return (
    <Wrap bare={bare}>
      <CardTitle icon={<Gavel className="size-4 text-brand" />} hint={`Awaiting ${who} · expires ${date(rec.expires_at)}`}>
        Your decision
      </CardTitle>

      {!user ? (
        <p className="text-sm text-muted-ink">Connecting to the server…</p>
      ) : !mayDecide ? (
        <p className="text-sm text-muted-ink">
          Signed in as {ROLES.find((r) => r.value === user.role)?.label}. Only {who} (or an admin) can decide this case.
        </p>
      ) : (
        <div className="space-y-5">
          <div className="rounded-xl bg-brand-soft p-4">
            <p className="text-xs font-bold tracking-wider text-muted-ink uppercase">You are approving</p>
            <p className="mt-1 text-sm leading-snug text-ink">
              {best && (rec.action === "contact_and_quote" || rec.action === "nurture" || rec.action === "refer_to_underwriter") ? (
                <>
                  Offer <strong className="font-bold">{best}</strong>
                </>
              ) : (
                <strong className="font-bold">{ACTION[rec.action] ?? rec.action}</strong>
              )}
            </p>
            {best && (
              <p className="mt-0.5 text-sm text-ink-2">
                Next step: <span className="font-semibold text-brand">{ACTION[action] ?? action}</span>
              </p>
            )}
          </div>

          {must.length > 0 ? (
            <div>
              <p className="mb-2 flex items-center gap-1.5 text-sm font-bold text-ink">
                <AlertTriangle className="size-4 text-warn" aria-hidden /> Check before approving
              </p>
              <ul className="space-y-2">
                {must.map((c, i) => (
                  <li key={i}>
                    <label className="flex cursor-pointer gap-2.5 rounded-lg border border-rule p-3 text-sm has-[:checked]:border-ok has-[:checked]:bg-ok-soft">
                      <input
                        type="checkbox"
                        className="mt-0.5 size-4 shrink-0 accent-brand"
                        checked={ticked.has(i)}
                        onChange={() => {
                          const next = new Set(ticked);
                          if (next.has(i)) next.delete(i);
                          else next.add(i);
                          setTicked(next);
                        }}
                      />
                      <span>
                        <span className="font-semibold text-ink">{c.title}</span>
                        {c.detail && <span className="block text-ink-2">{c.detail}</span>}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="flex items-center gap-2 text-sm font-semibold text-ok">
              <CheckCircle2 className="size-4" aria-hidden /> No flags. Ready to approve.
            </p>
          )}

          {notes.length > 0 && (
            <ul className="space-y-1.5 text-xs leading-relaxed text-muted-ink">
              {notes.slice(0, 3).map((c, i) => (
                <li key={i} className="flex gap-1.5">
                  <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                  <span>
                    <span className="font-semibold text-ink-2">{c.title}.</span> {c.detail}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {mode === "edit" && (
            <div className="space-y-2 rounded-xl bg-ice p-3">
              <p className="text-xs font-bold text-muted-ink">Change the next step, then approve</p>
              <div className="flex flex-wrap gap-2">
                {EDITABLE.filter((a) => a !== rec.action).map((a) => (
                  <button
                    key={a}
                    onClick={() => setAction(a)}
                    className={cx("rounded-full border px-3.5 py-1.5 text-sm font-semibold", action === a ? "border-brand bg-brand-soft text-brand" : "border-rule bg-card text-ink-2")}
                  >
                    {ACTION[a]}
                  </button>
                ))}
              </div>
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Why (optional)"
                className="w-full rounded-lg border border-rule bg-card px-3 py-2 text-sm outline-none focus:border-brand"
              />
            </div>
          )}
          {mode === "reject" && (
            <div className="space-y-2 rounded-xl bg-ice p-3">
              <p className="text-xs font-bold text-muted-ink">Why are you rejecting it? (required)</p>
              <div className="flex flex-wrap gap-1.5">
                {REASONS.map((r) => (
                  <button key={r} onClick={() => setReason(r)} className={cx("rounded-full border px-3 py-1 text-xs font-semibold", reason === r ? "border-brand bg-brand-soft text-brand" : "border-rule bg-card text-ink-2")}>
                    {r}
                  </button>
                ))}
              </div>
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Or write a reason"
                className="w-full rounded-lg border border-rule bg-card px-3 py-2 text-sm outline-none focus:border-brand"
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
                    <Pencil className="size-4" /> Change next step
                  </Button>
                )}
                <Button variant="ghost" onClick={() => setMode("reject")}>
                  <X className="size-4" /> Reject
                </Button>
              </>
            )}
            {mode === "edit" && (
              <>
                <Button busy={decide.isPending} disabled={!allTicked || action === rec.action} onClick={() => decide.mutate("edit")}>
                  <Check className="size-4" /> Approve as {ACTION[action] ?? action}
                </Button>
                <Button variant="ghost" onClick={() => { setMode("idle"); setAction(rec.action); }}>
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
          {!allTicked && mode !== "reject" && <p className="text-xs text-muted-ink">Tick the checks above to approve.</p>}
        </div>
      )}
    </Wrap>
  );
}
