"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Bot, CheckCircle2, CircleDashed, FileText, Info, ListChecks, Mail, Package, Phone, Play, RotateCw, ShieldAlert, UserRound } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { type ReactNode, Suspense, use, useEffect } from "react";
import { DecisionPanel } from "@/components/decision";
import { Avatar, Facts, RiskBadge, Section } from "@/components/kit";
import { Badge, Button, Card, cx, ErrorBox, Skeleton } from "@/components/ui";
import { ACTIVE_RUN, api, type Approachability, type Checklist, type CrossSell, type Justification, type LeadDetail, type RankedProduct, type NextStep, type RecDetail, type ScoreDecision } from "@/lib/api";
import { ACTION, ageFrom, date, human, LINE, money, OWNER, TEAM } from "@/lib/format";
import { useRunLead } from "@/lib/hooks";
import { eligibility, PRIORITY, REC_STATUS } from "@/lib/leads";

type Decisions = Record<string, ScoreDecision | undefined>;
const yesNo = (b: boolean | null | undefined) => (b ? "Yes" : "No");

// Where "Back" returns to: the list the customer was opened from.
const BACK: Record<string, [string, string]> = {
  dashboard: ["/dashboard", "Back to Prospect Dashboard"],
  prospects: ["/prospects", "Back to Prospect Discovery"],
  risk: ["/risk", "Back to Risk Assessment"],
  products: ["/products", "Back to Product Matching"],
  priorities: ["/priorities", "Back to Lead Prioritization"],
  engagement: ["/engagement", "Back to Sales Engagement"],
};

export default function CustomerPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <Customer id={use(params).id} />
    </Suspense>
  );
}

function Customer({ id }: { id: string }) {
  const [backHref, backLabel] = BACK[useSearchParams().get("from") ?? ""] ?? BACK.prospects;
  const lead = useQuery({
    queryKey: ["lead", id],
    queryFn: () => api<LeadDetail>(`/leads/${id}`),
    refetchInterval: (q) => (ACTIVE_RUN.includes(q.state.data?.latest_run?.status ?? "") ? 2_000 : 30_000),
  });
  const recId = lead.data?.latest_recommendation?.id;
  const rec = useQuery({ queryKey: ["rec", recId], queryFn: () => api<RecDetail>(`/recommendations/${recId}`), enabled: !!recId });
  const run = useRunLead();

  // Open at the section the list pointed to (#risk, #products, ...) once its content has loaded.
  const ready = !!lead.data && (!recId || !!rec.data);
  useEffect(() => {
    const target = window.location.hash.slice(1);
    if (ready && target) document.getElementById(target)?.scrollIntoView({ block: "start" });
  }, [ready]);

  if (lead.error) return <ErrorBox error={lead.error} />;
  if (lead.isPending) return <Skeleton className="h-96" />;

  const l = lead.data;
  const r = rec.data;
  const running = run.isPending || ACTIVE_RUN.includes(l.latest_run?.status ?? "");
  const st = r ? REC_STATUS[r.status] : undefined;

  return (
    <>
      <Link href={backHref} className="mb-4 inline-flex items-center gap-1.5 text-sm font-semibold text-brand hover:underline">
        <ArrowLeft className="size-4" aria-hidden /> {backLabel}
      </Link>

      <Card className="mb-5">
        <div className="flex flex-wrap items-center gap-4">
          <Avatar name={l.name} size={14} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="font-display text-xl font-bold text-ink">{l.name || "Unnamed customer"}</h1>
              {l.product_line && <Badge tone="brand">{LINE[l.product_line] ?? l.product_line}</Badge>}
              {l.existing_customer && <Badge tone="green">Existing customer</Badge>}
              <span className="text-sm text-muted-ink">{l.external_ref ?? l.id}</span>
            </div>
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-ink">
              {l.email && (
                <span className="flex items-center gap-1.5">
                  <Mail className="size-3.5" aria-hidden /> {l.email}
                </span>
              )}
              {l.phone && (
                <span className="flex items-center gap-1.5">
                  <Phone className="size-3.5" aria-hidden /> {l.phone}
                </span>
              )}
            </div>
          </div>
          {st && <Badge tone={st.tone}>{st.label}</Badge>}
          <Button variant={r ? "ghost" : "primary"} busy={running} onClick={() => run.mutate(l.id)}>
            {!running && (r ? <RotateCw className="size-4" /> : <Play className="size-4" />)}
            {running ? "Agents working…" : r ? "Run agents again" : "Run agents"}
          </Button>
        </div>
        {r && (
          <nav aria-label="On this page" className="mt-4 flex flex-wrap gap-1.5 border-t border-rule pt-4 text-sm">
            {[
              ["#summary", "Summary"],
              ["#products", "Products"],
              ["#risk", "Risk"],
              ["#next-steps", "Next steps"],
              ["#ai", "How the agents decided"],
              ["#decision", "Decision"],
            ].map(([href, label]) => (
              <a key={href} href={href} className="rounded-lg bg-ice px-3 py-1.5 font-semibold text-ink-2 hover:bg-brand-soft hover:text-brand">
                {label}
              </a>
            ))}
          </nav>
        )}
      </Card>

      {l.latest_run?.status === "failed" && !running && (
        <div className="mb-5">
          <ErrorBox error={new Error(`The last run failed (${l.latest_run.error_code}). Run the agents again.`)} />
        </div>
      )}
      {rec.error && <ErrorBox error={rec.error} />}

      <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
        <div className="space-y-5">
          {!r ? (
            <Card>
              <p className="text-sm text-ink-2">{running ? "The agents are checking this customer. The page updates by itself." : "The agents have not checked this customer yet."}</p>
            </Card>
          ) : (
            <>
              <Summary rec={r} />
              <Products rec={r} />
              <Risk rec={r} />
              <NextSteps rec={r} />
              <HowDecided rec={r} lead={l} />
            </>
          )}
        </div>

        <div className="space-y-5">
          {r && (
            <div id="decision" className="scroll-mt-20">
              <DecisionPanel key={r.id} rec={r} />
            </div>
          )}
          <Section id="details" icon={<UserRound className="size-4.5" />} title="Customer">
            <Facts
              rows={[
                ["Interested in", LINE[l.product_line ?? ""] ?? "—"],
                ["Cover requested", money(l.sum_insured)],
                ["Age", ageFrom(l.dob) ?? "—"],
                ["City", l.city ?? "—"],
                ["Source", human(l.source)],
                ["Handled by", `${OWNER[l.channel_owner] ?? l.channel_owner}${l.intermediary ? ` · ${l.intermediary}` : ""}`],
                ["Added", date(l.created_at)],
              ]}
            />
          </Section>
          <Section id="consent" icon={<ShieldAlert className="size-4.5" />} title="Contact & consent">
            <Facts
              rows={[
                ["Profiling allowed", yesNo(l.consent_profiling)],
                ["Offers allowed", yesNo(l.consent_marketing)],
                ["Email allowed", yesNo(l.consent_email)],
                ["SMS allowed", yesNo(l.consent_sms)],
              ]}
            />
          </Section>
          <Documents lead={l} rec={r} />
        </div>
      </div>
    </>
  );
}

/* --------------------------------------------------------------- summary */

function Summary({ rec }: { rec: RecDetail }) {
  const j = (rec.justification ?? {}) as Justification;
  const reach = rec.approachability as Approachability;
  const risk = (rec.decisions as Decisions).risk;
  const p = PRIORITY[rec.priority];
  return (
    <Section id="summary" icon={<Info className="size-4.5" />} title="What the agents found">
      {j.headline && <p className="text-sm font-semibold text-ink">{j.headline}</p>}
      {rec.explanation && <p className="mt-1 text-sm text-ink-2">{rec.explanation}</p>}
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <Box label="Lead score" value={typeof reach.score === "number" ? `${reach.score} / 100` : "Not scored"} note={reach.label} />
        <Box label="Risk" value={risk?.band ? `${human(risk.band)} risk` : "Not rated"} note={typeof risk?.score === "number" ? `${Math.round(risk.score * 100)} / 100` : undefined} />
        <Box label="Suggested next step" value={ACTION[rec.action] ?? human(rec.action)} note={p ? `${p.label} priority` : undefined} brand />
      </div>
    </Section>
  );
}

function Box({ label, value, note, brand }: { label: string; value: string; note?: string; brand?: boolean }) {
  return (
    <div className={cx("rounded-lg p-3", brand ? "bg-brand-soft" : "bg-ice")}>
      <p className="text-xs text-muted-ink">{label}</p>
      <p className={cx("mt-0.5 font-semibold", brand ? "text-brand" : "text-ink")}>{value}</p>
      {note && <p className="mt-0.5 text-xs text-ink-2">{note}</p>}
    </div>
  );
}

/* -------------------------------------------------------------- products */

function Products({ rec }: { rec: RecDetail }) {
  const products = (rec.products ?? []) as RankedProduct[];
  const extra = (rec.cross_sell ?? []) as CrossSell[];
  return (
    <Section id="products" icon={<Package className="size-4.5" />} title="Matched products">
      {products.length === 0 ? (
        <p className="text-sm text-muted-ink">No product matched ({ACTION[rec.action] ?? human(rec.action)}).</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {products.map((p, i) => (
            <Product key={p.code} name={p.name ?? p.code} text={p.rationale} best={i === 0} badge={i === 0 ? <Badge tone="brand">Best fit</Badge> : <Badge tone="gray">{human(p.fit ?? "")} fit</Badge>} />
          ))}
          {extra.map((x) => (
            <Product key={x.code} name={x.name ?? x.code} text={x.rationale} badge={<Badge tone={x.needs_underwriter ? "amber" : "blue"}>{x.needs_underwriter ? "Needs a risk check" : "Also suits"}</Badge>} />
          ))}
        </div>
      )}
    </Section>
  );
}

function Product({ name, text, badge, best }: { name: string; text?: string; badge: ReactNode; best?: boolean }) {
  return (
    <div className={cx("rounded-xl border p-4", best ? "border-brand bg-brand-soft" : "border-rule")}>
      <div className="flex items-start justify-between gap-2">
        <p className="font-semibold text-ink">{name}</p>
        {badge}
      </div>
      {text && <p className="mt-1 text-xs text-ink-2">{text}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------ risk */

function Risk({ rec }: { rec: RecDetail }) {
  const risk = (rec.decisions as Decisions).risk;
  const refer = rec.action === "refer_to_underwriter";
  return (
    <Section id="risk" icon={<ShieldAlert className="size-4.5" />} title="Risk" action={<RiskBadge band={risk?.band} />}>
      <p className={cx("text-sm font-semibold", refer ? "text-warn" : "text-ok")}>{refer ? "An underwriter must review this case first." : "No underwriter review needed."}</p>
      {risk?.reasons?.length ? (
        <ul className="mt-3 space-y-1.5 text-sm">
          {risk.reasons.slice(0, 3).map((x, i) => (
            <li key={`${x.signal}-${i}`} className="flex gap-2 text-ink-2">
              <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-brand" />
              {x.explanation}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-sm text-muted-ink">Not rated: the rules stopped this case before risk scoring.</p>
      )}
    </Section>
  );
}

/* ------------------------------------------------------------ next steps */

function NextSteps({ rec }: { rec: RecDetail }) {
  const steps = ((rec.next_steps ?? []) as NextStep[]).filter((s) => s.kind !== "approve");
  return (
    <Section id="next-steps" icon={<ListChecks className="size-4.5" />} title="Next steps">
      {steps.length === 0 ? (
        <p className="text-sm text-muted-ink">No next steps for this case.</p>
      ) : (
        <ol className="space-y-3">
          {steps.map((s, i) => (
            <li key={i} className="flex gap-3 text-sm">
              <span className={cx("grid size-6 shrink-0 place-items-center rounded-full text-xs font-semibold", s.kind === "stop" ? "bg-bad-soft text-bad" : "bg-brand-soft text-brand")}>{i + 1}</span>
              <div className="min-w-0">
                <p className="font-semibold text-ink">
                  {s.title} <span className="font-normal text-muted-ink">· {s.owner}</span>
                </p>
                {s.detail && <p className="text-ink-2">{s.detail}</p>}
                {s.quote && <p className="mt-1.5 rounded-lg bg-ice p-2 text-ink">&ldquo;{s.quote}&rdquo;</p>}
              </div>
            </li>
          ))}
        </ol>
      )}
    </Section>
  );
}

/* ------------------------------------------------------- how it decided */

function HowDecided({ rec, lead }: { rec: RecDetail; lead: LeadDetail }) {
  const d = rec.decisions as Decisions;
  const e = eligibility(lead);
  const best = ((rec.products ?? []) as RankedProduct[])[0];
  const reach = rec.approachability as Approachability;
  const refer = rec.action === "refer_to_underwriter";
  const steps: { agent: string; done: boolean; ai?: boolean; text: string }[] = [
    { agent: "Prospect agent", done: true, text: e.key === "blocked" ? `${e.label}: the case stops here.` : "Consent and data checks passed." },
    {
      agent: "Risk agent",
      done: !!d.risk || refer,
      ai: !!d.risk,
      text: d.risk?.band ? `${human(d.risk.band)} risk${refer ? ", referred to an underwriter" : ""}.` : refer ? "Knock-out rule hit: referred to an underwriter." : "Not needed.",
    },
    { agent: "Scoring agent", done: !!d.lead_score, ai: true, text: d.lead_score?.band ? `${human(d.lead_score.band)} buying interest · ${reach.label}.` : "Not needed." },
    { agent: "Product agent", done: !!best, ai: true, text: best ? `Best fit: ${best.name ?? best.code}.` : "No product matched." },
    { agent: "Engagement agent", done: true, text: `${ACTION[rec.action] ?? human(rec.action)} · decided by ${(TEAM[rec.queue] ?? rec.queue).toLowerCase()}.` },
  ];
  return (
    <Section id="ai" icon={<Bot className="size-4.5" />} title="How the agents decided">
      <ol className="space-y-3">
        {steps.map((s) => (
          <li key={s.agent} className="flex gap-3 text-sm">
            {s.done ? <CheckCircle2 className="mt-0.5 size-4.5 shrink-0 text-ok" aria-label="done" /> : <CircleDashed className="mt-0.5 size-4.5 shrink-0 text-faint" aria-label="not needed" />}
            <div>
              <p className="font-semibold text-ink">
                {s.agent}
                {s.ai && s.done && <span className="ml-1.5 text-xs font-semibold text-brand">AI</span>}
              </p>
              <p className="text-ink-2">{s.text}</p>
            </div>
          </li>
        ))}
      </ol>
    </Section>
  );
}

/* ------------------------------------------------------------- documents */

function Documents({ lead, rec }: { lead: LeadDetail; rec?: RecDetail }) {
  const c = (rec?.checklist ?? {}) as Checklist;
  const missing = c.documents_missing ?? [];
  const have = lead.documents_provided ?? [];
  return (
    <Section id="documents" icon={<FileText className="size-4.5" />} title="Documents">
      {missing.length === 0 && have.length === 0 ? (
        <p className="text-sm text-muted-ink">No documents on file.</p>
      ) : (
        <ul className="space-y-1.5 text-sm">
          {have.map((m) => (
            <li key={m} className="flex items-center gap-2 text-ink">
              <CheckCircle2 className="size-4 text-ok" aria-hidden /> {human(m)}
            </li>
          ))}
          {missing.map((m) => (
            <li key={m} className="flex items-center gap-2 text-ink">
              <CircleDashed className="size-4 text-warn" aria-hidden /> {human(m)} <span className="text-xs text-muted-ink">missing</span>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
