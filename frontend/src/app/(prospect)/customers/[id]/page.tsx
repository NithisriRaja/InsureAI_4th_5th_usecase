"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CalendarDays,
  CheckCircle2,
  ClipboardList,
  Clock,
  Gauge,
  Info,
  Lightbulb,
  ListChecks,
  Mail,
  Package,
  Phone,
  Play,
  RotateCw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  UserRound,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type ReactNode, Suspense, use, useEffect, useState } from "react";
import { AgentProgress } from "@/components/agent-progress";
import { DecisionPanel } from "@/components/decision";
import { Avatar, Facts, RiskBadge } from "@/components/kit";
import { Badge, Button, Card, cx, ErrorBox, Skeleton } from "@/components/ui";
import {
  ACTIVE_RUN,
  api,
  type Approachability,
  type CrossSell,
  type Justification,
  type LeadDetail,
  type NextStep,
  type Reason,
  type RecDetail,
  type Screened,
  type ScoreDecision,
} from "@/lib/api";
import { ACTION, ageFrom, date, human, LINE, money, OWNER } from "@/lib/format";
import { DeleteCustomer } from "@/components/delete-customer";
import { useRunLead } from "@/lib/hooks";
import { PRIORITY, REC_STATUS } from "@/lib/leads";

type Decisions = Record<string, ScoreDecision | undefined>;
type ProductFit = { confidence_score?: number | null; confidence_reason?: string | null; reasons?: Reason[]; watch_out?: string | null; justification?: string | null; talking_points?: Reason[]; pain_points?: Reason[] };

// Where "Back" returns to: the list the customer was opened from.
const BACK: Record<string, [string, string]> = {
  apply: ["/apply", "New application"],
  dashboard: ["/dashboard", "Back to Prospect Dashboard"],
  prospects: ["/prospects", "Back to Prospect Discovery"],
  products: ["/products", "Back to Product Matching"],
  engagement: ["/engagement", "Back to Sales Engagement"],
};

const TABS: [string, string][] = [
  ["#summary", "AI recommendation"],
  ["#why", "Why this policy"],
  ["#products", "Why not the others"],
  ["#risk", "Risk"],
  ["#next-steps", "Next steps"],
  ["#decision", "Decision"],
];

export default function CustomerPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <Customer id={use(params).id} />
    </Suspense>
  );
}

function Customer({ id }: { id: string }) {
  const router = useRouter();
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
  const failed = l.latest_run?.status === "failed" && !running;
  const st = r ? REC_STATUS[r.status] : undefined;

  return (
    <>
      <Link href={backHref} className="mb-3 inline-flex items-center gap-1.5 text-sm font-semibold text-brand hover:underline">
        <ArrowLeft className="size-4" aria-hidden /> {backLabel}
      </Link>

      <Card className="mb-5 !p-0">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-3 px-5 py-3.5">
          <Avatar name={l.name} size={10} />
          <div className="min-w-0 flex-1 basis-72">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="font-display text-lg font-bold text-ink">{l.name || "Unnamed customer"}</h1>
              {l.product_line && <Badge tone="brand">{LINE[l.product_line] ?? l.product_line}</Badge>}
              {l.existing_customer && <Badge tone="green">Existing customer</Badge>}
            </div>
            <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-ink">
              {l.email && (
                <span className="inline-flex items-center gap-1">
                  <Mail className="size-3" aria-hidden /> {l.email}
                </span>
              )}
              {l.phone && (
                <span className="inline-flex items-center gap-1">
                  <Phone className="size-3" aria-hidden /> {l.phone}
                </span>
              )}
              <span className="inline-flex items-center gap-1">
                <CalendarDays className="size-3" aria-hidden /> Created {date(l.created_at)}
              </span>
              {r && (
                <span className="inline-flex items-center gap-1">
                  <Clock className="size-3" aria-hidden /> Analysed {date(r.created_at)}
                </span>
              )}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {running ? <Badge tone="blue">Agents working…</Badge> : failed ? <Badge tone="red">Last run failed</Badge> : r && <Badge tone="green">AI analysis complete</Badge>}
            {st && <Badge tone={st.tone}>{st.label}</Badge>}
            <Button variant={r ? "ghost" : "primary"} busy={running} onClick={() => run.mutate(l.id)}>
              {!running && (r ? <RotateCw className="size-4" /> : <Play className="size-4" />)}
              {running ? "Agents working…" : r ? "Run agents again" : "Run agents"}
            </Button>
            <DeleteCustomer id={l.id} name={l.name} onDeleted={() => router.push(backHref)} className="border border-rule" />
          </div>
        </div>
        {r && (
          <nav aria-label="On this page" className="flex gap-0.5 overflow-x-auto border-t border-rule px-3 text-[13px]">
            {TABS.map(([href, label], i) => (
              <a
                key={href}
                href={href}
                className={cx("shrink-0 border-b-2 px-3 py-2 font-semibold transition-colors", i === 0 ? "border-brand text-brand" : "border-transparent text-muted-ink hover:text-ink")}
              >
                {label}
              </a>
            ))}
          </nav>
        )}
      </Card>

      {failed && (
        <div className="mb-6">
          <ErrorBox error={new Error(`The last run failed (${l.latest_run?.error_code}). Run the agents again.`)} />
        </div>
      )}
      {rec.error && <ErrorBox error={rec.error} />}

      <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
        <div className="min-w-0 space-y-6">
          {!r ? (
            running ? (
              <AgentProgress name={l.first_name} />
            ) : (
              <Card>
                <p className="text-sm text-ink-2">The agents have not checked this customer yet.</p>
              </Card>
            )
          ) : (
            <>
              <Hero rec={r} />
              <WhyThis rec={r} />
              <WhyNot rec={r} />
              <Risk rec={r} />
            </>
          )}
        </div>

        <div className="min-w-0 space-y-6">
          {r && (
            <div id="decision" className="scroll-mt-20">
              <DecisionPanel key={r.id} rec={r} />
            </div>
          )}
          <Panel id="details" icon={<UserRound className="size-5" />} title="Customer">
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
          </Panel>
          <Panel id="consent" icon={<ShieldAlert className="size-5" />} title="Contact & consent">
            <ul className="divide-y divide-rule text-sm">
              {(
                [
                  ["Profiling allowed", l.consent_profiling],
                  ["Offers allowed", l.consent_marketing],
                  ["Email allowed", l.consent_email],
                  ["SMS allowed", l.consent_sms],
                ] as [string, boolean][]
              ).map(([k, v]) => (
                <li key={k} className="flex items-center justify-between py-2.5">
                  <span className="text-muted-ink">{k}</span>
                  <span className={cx("flex items-center gap-1.5 font-semibold", v ? "text-ok" : "text-muted-ink")}>
                    {v ? <CheckCircle2 className="size-4" aria-hidden /> : <XCircle className="size-4" aria-hidden />}
                    {v ? "Yes" : "No"}
                  </span>
                </li>
              ))}
            </ul>
          </Panel>
          {r && <NextSteps rec={r} />}
        </div>
      </div>
    </>
  );
}

/* ---------------------------------------------------------------- building blocks */

function Panel({ id, icon, title, action, children }: { id?: string; icon: ReactNode; title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-20 rounded-2xl border border-rule bg-card p-6 shadow-card">
      <header className="mb-5 flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2.5 font-display text-lg font-bold text-ink">
          <span className="text-brand">{icon}</span>
          {title}
        </h2>
        {action}
      </header>
      {children}
    </section>
  );
}

/** Text with every mention of the policy name in bold. */
function boldName(text: string, name?: string | null): ReactNode {
  if (!name) return text;
  return text.split(name).flatMap((part, i, all) => (i < all.length - 1 ? [part, <strong key={i} className="font-bold text-ink">{name}</strong>] : [part]));
}

/** Long text shows its first two lines, with a toggle to read the rest. */
function Clamp({ children, long }: { children: ReactNode; long: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <p className={cx("mt-1.5 text-sm leading-6 font-medium text-ink", long && !open && "line-clamp-2")}>{children}</p>
      {long && (
        <button type="button" onClick={() => setOpen(!open)} className="mt-1 text-xs font-semibold text-brand hover:underline">
          {open ? "Show less" : "Read more"}
        </button>
      )}
    </>
  );
}

function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="text-xs font-bold tracking-wider text-muted-ink uppercase">{children}</p>;
}

/* ------------------------------------------------------------------ hero */

const CONFIDENCE: Record<string, number> = { high: 1, medium: 0.66, low: 0.33 };

/** A ring showing how sure the AI is of its policy pick: the number it reported, or its level (high / medium / low) on older results. */
function Ring({ level, score, reason, watchOut }: { level: string; score?: number | null; reason?: string | null; watchOut?: string | null }) {
  const [open, setOpen] = useState(false);
  const generic = { high: "The facts given match this policy clearly, and no other policy comes close.", medium: "The policy fits, but a few answers are borderline or another policy is close behind.", low: "Important facts are missing or unclear, so a person should look closely before relying on this." }[level] ?? "";
  const fill = typeof score === "number" ? score / 100 : (CONFIDENCE[level] ?? 0);
  const c = 2 * Math.PI * 44;
  return (
    <div className="text-center">
      <div className="relative size-24">
        <svg viewBox="0 0 100 100" className="size-full -rotate-90" aria-hidden>
          <circle cx="50" cy="50" r="44" fill="none" strokeWidth="8" className="stroke-ice-2" />
          <circle cx="50" cy="50" r="44" fill="none" strokeWidth="8" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - fill)} className="stroke-brand" />
        </svg>
        <span className="absolute inset-0 grid place-items-center font-display text-base font-bold text-ink">{typeof score === "number" ? `${score}%` : human(level)}</span>
      </div>
      <div className="relative mt-1.5 flex items-start justify-center gap-1">
        <p className="max-w-24 text-xs font-semibold text-muted-ink">AI confidence in this policy</p>
        <button type="button" aria-label="Why this confidence?" aria-expanded={open} onClick={() => setOpen(!open)} className="grid size-5 shrink-0 place-items-center rounded-full text-muted-ink hover:bg-ice hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40">
          <Info className="size-3.5" aria-hidden />
        </button>
        {open && (
          <div role="dialog" className="absolute top-full right-0 z-20 mt-2 w-64 rounded-xl border border-rule bg-card p-3.5 text-left text-xs leading-relaxed font-normal text-ink-2 shadow-lg">
            <p className="mb-1 text-sm font-bold text-ink">Why {typeof score === "number" ? `${score}%` : human(level)}?</p>
            <p>{reason || generic}</p>
            {watchOut && <p className="mt-1.5 text-ink-2">Check: {watchOut}</p>}
          </div>
        )}
      </div>
    </div>
  );
}

function Hero({ rec }: { rec: RecDetail }) {
  const j = (rec.justification ?? {}) as Justification;
  const reach = rec.approachability as Approachability;
  const risk = (rec.decisions as Decisions).risk;
  const p = PRIORITY[rec.priority];
  const best = ((rec.product_screening ?? []) as Screened[]).find((x) => x.requested_line && x.ai_status === "recommended");
  const fit = (rec.decisions as Record<string, unknown>).product_fit as ProductFit | undefined;
  const reasons = (fit?.reasons ?? []).slice(0, 5);
  const concerns = (risk?.reasons ?? []).slice(0, 2);
  const first = rec.subject_name?.split(" ")[0] ?? "this customer";
  return (
    <section id="summary" className="scroll-mt-20 rounded-2xl border border-rule bg-card p-5 shadow-card sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div className="min-w-0 flex-1 basis-80">
          <p className="flex items-center gap-1.5 text-xs font-bold tracking-wider text-brand uppercase">
            <Sparkles className="size-3.5" aria-hidden /> What the agents found
          </p>
          {best ? (
            <>
              <h2 className="mt-1.5 font-display text-2xl leading-tight font-bold text-ink">{best.name}</h2>
              <div className="mt-2 flex flex-wrap gap-2">
                <Badge tone="brand">Recommended policy</Badge>
                {best.fit && <Badge tone="green">{human(best.fit)} fit</Badge>}
              </div>
            </>
          ) : (
            <>
              <h2 className="mt-2 font-display text-2xl leading-tight font-bold text-ink">{j.headline ?? "No policy was picked"}</h2>
              <div className="mt-2">
                <Badge tone="amber">No policy picked</Badge>
              </div>
            </>
          )}
        </div>
        <div className="flex items-center gap-5">
          {rec.confidence && <Ring level={rec.confidence} score={fit?.confidence_score} reason={fit?.confidence_reason} watchOut={fit?.watch_out} />}
          {risk?.band && (
            <div className="text-center">
              <RiskBadge band={risk.band} />
              <p className="mt-1.5 text-xs font-semibold text-muted-ink">Risk level</p>
            </div>
          )}
        </div>
      </div>

      {best && reasons.length > 0 ? (
        <div className="mt-4">
          <div className="rounded-xl border border-brand/30 border-l-4 border-l-brand bg-brand-soft px-4 py-3 shadow-sm">
            <p className="flex items-center gap-1.5 text-xs font-bold tracking-wider text-brand uppercase">
              <Sparkles className="size-3.5" aria-hidden /> Why we picked this for {first}
            </p>
            <Clamp long={(fit?.justification ?? reasons.map((x) => x.explanation).join(" ")).length > 380}>{boldName(fit?.justification ?? reasons.map((x) => x.explanation).join(" "), best?.name)}</Clamp>
            {!fit?.justification && <p className="mt-2 text-xs text-muted-ink">This is an older result. Click &ldquo;Run agents again&rdquo; to get the full story.</p>}
          </div>
          {concerns.length > 0 && (
            <>
              <div className="mt-5">
                <Eyebrow>Keep in mind</Eyebrow>
              </div>
              <p className="mt-1.5 text-sm leading-6 text-ink-2">{concerns.map((x) => x.explanation).join(" ")}</p>
            </>
          )}
        </div>
      ) : (
        rec.explanation && <p className="mt-4 text-sm leading-relaxed text-ink-2">{rec.explanation}</p>
      )}
      {fit?.watch_out && (
        <p className="mt-4 flex gap-2 rounded-xl bg-ice p-3 text-sm text-ink-2">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn" aria-hidden />
          <span>
            <strong className="text-ink">Check before quoting:</strong> {fit.watch_out}
          </span>
        </p>
      )}

      <div className="mt-7 grid gap-px overflow-hidden rounded-xl border border-rule bg-rule sm:grid-cols-3">
        <Stat icon={<Gauge className="size-5" />} label="Lead score" value={typeof reach.score === "number" ? `${reach.score} / 100` : "Not scored"} note={reach.label} />
        <Stat icon={<ShieldCheck className="size-5" />} label="Risk level" value={risk?.band ? human(risk.band) : "Not rated"} note={typeof risk?.score === "number" ? `${Math.round(risk.score * 100)} / 100` : undefined} />
        <Stat icon={<ClipboardList className="size-5" />} label="Suggested next step" value={ACTION[rec.action] ?? human(rec.action)} note={p ? `${p.label} priority` : undefined} brand />
      </div>
    </section>
  );
}

function Stat({ icon, label, value, note, brand }: { icon: ReactNode; label: string; value: string; note?: string; brand?: boolean }) {
  return (
    <div className="flex items-center gap-3 bg-card p-4">
      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-ice text-muted-ink">{icon}</span>
      <div className="min-w-0">
        <p className="text-xs text-muted-ink">{label}</p>
        <p className={cx("text-base font-bold", brand ? "text-brand" : "text-ink")}>{value}</p>
        {note && <p className="text-xs text-ink-2">{note}</p>}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- why this */

const HIDE = new Set(["product_line", "channel_owner", "currency", "source", "existing_customer", "quote_requests_30d", "pages_viewed", "requested_callback", "days_since_inquiry"]);
const CASH = new Set(["sum_insured", "annual_income", "vehicle_value", "rebuild_value", "existing_cover", "monthly_budget", "home_loan_outstanding"]);

function fact(key: string, v: unknown, currency: string): string {
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (Array.isArray(v)) return v.length ? v.map((x) => human(String(x))).join(", ") : "None";
  if (typeof v === "number") return CASH.has(key) ? `${currency} ${v.toLocaleString()}` : key.endsWith("_pct") ? `${v}%` : String(v);
  return human(String(v));
}

const LABEL: Record<string, string> = { bmi: "BMI", sum_insured: "Cover asked for", pre_existing_conditions: "Existing conditions", age_band: "Age group", dependents: "Dependants", term_years: "Plan length (years)" };

/** Turns a rule check such as "Aged 44: the product covers ages 18 to 55" into a friendly sentence. */
function friendly(line: string, first: string): string {
  const t = line.replace(/\.$/, "");
  const m = (re: RegExp) => t.match(re);
  let r: RegExpMatchArray | null;
  if ((r = m(/^Aged (\d+): the product covers ages (\d+) to (\d+)$/))) return `${first} is ${r[1]}, well within the ages this policy accepts (${r[2]} to ${r[3]}).`;
  if ((r = m(/^Asked for (.+?) of cover: the product offers (.+?) to (.+)$/))) return `The ${r[1]} of cover they asked for sits inside what the policy offers (${r[2]} to ${r[3]}).`;
  if ((r = m(/^Car is (\d+) years old: accepted up to (\d+)$/))) return `Their car is ${r[1]} years old, and the policy takes cars up to ${r[2]} years.`;
  if ((r = m(/^Has driven for (\d+) years: needs at least (\d+)$/))) return `They have been driving for ${r[1]} years, and the policy asks for at least ${r[2]}.`;
  if ((r = m(/^Home is (\d+) years old: accepted up to (\d+)$/))) return `Their home is ${r[1]} years old, and the policy accepts homes up to ${r[2]} years.`;
  if ((r = m(/^Has (\d+) dependant\(s\): needs at least (\d+)$/))) return `They have ${r[1]} ${r[1] === "1" ? "dependant" : "dependants"} to look after, and the policy needs at least ${r[2]}.`;
  if ((r = m(/^Plan of (\d+) years: needs at least (\d+)$/))) return `They want a ${r[1]}-year plan, and the policy needs at least ${r[2]} years.`;
  if ((r = m(/^Plan ends at age (\d+): must end by (\d+)$/))) return `The plan would finish when they are ${r[1]}, comfortably before the policy's limit of ${r[2]}.`;
  if ((r = m(/^(\d+) staff: the scheme needs at least (\d+)$/))) return `The company has ${r[1]} staff, and the scheme needs at least ${r[2]}.`;
  if (t === "We can sell it to them directly") return "We can sell this policy to them directly, so there is no middleman.";
  if (t === "Their broker can sell this product") return "Their broker can arrange this policy for them.";
  if (t === "It is offered through their employer") return "This policy is offered through their employer.";
  if (t === "A licensed adviser can arrange it") return "A licensed adviser can arrange this policy for them.";
  return `${t}.`;
}

function WhyThis({ rec }: { rec: RecDetail }) {
  const signals = (rec.signals ?? {}) as Record<string, unknown>;
  const currency = typeof signals.currency === "string" ? signals.currency : "";
  const facts = Object.entries(signals)
    .filter(([k, v]) => !HIDE.has(k) && v !== null && v !== undefined && v !== "")
    .slice(0, 7);
  const best = ((rec.product_screening ?? []) as Screened[]).find((x) => x.requested_line && x.ai_status === "recommended");
  const qualifies = best?.evidence ?? [];
  const first = rec.subject_name?.split(" ")[0] ?? "The customer";
  return (
    <Panel id="why" icon={<Lightbulb className="size-5" />} title="Why the AI recommends this">
      <div className="grid gap-4 lg:grid-cols-2">
        <Column title="Key evidence">
          {facts.length === 0 ? (
            <p className="text-sm text-muted-ink">No facts were passed to the AI for this case.</p>
          ) : (
            <dl className="divide-y divide-rule text-sm">
              {facts.map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3 py-2">
                  <dt className="text-muted-ink">{LABEL[k] ?? human(k)}</dt>
                  <dd className="text-right font-semibold text-ink">{fact(k, v, currency)}</dd>
                </div>
              ))}
            </dl>
          )}
        </Column>
        <div className="rounded-xl border border-ok/30 border-l-4 border-l-ok bg-ok-soft p-5">
          <p className="flex items-center gap-1.5 text-xs font-bold tracking-wider text-ok uppercase">
            <CheckCircle2 className="size-3.5" aria-hidden /> {best ? `How ${first} fits ${best.name}` : "Why it qualifies"}
          </p>
          {qualifies.length === 0 ? (
            <p className="mt-2.5 text-sm text-muted-ink">No policy was checked: the rules stopped this case first.</p>
          ) : (
            <div className="mt-2.5 space-y-3 text-sm leading-7 text-ink">
              <p>Here is how {first} measures up against what <strong className="font-bold">{best?.name}</strong> asks for. {qualifies.map((q) => friendly(q, first)).join(" ")}</p>
              <p className="rounded-lg bg-white/70 p-3 font-semibold">So on every rule we check, {first} qualifies, and that is why this policy stayed on the table.</p>
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}

function Column({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-rule p-4">
      <Eyebrow>{title}</Eyebrow>
      <div className="mt-3">{children}</div>
    </div>
  );
}

/* ------------------------------------------------------------- why not */

function WhyNot({ rec }: { rec: RecDetail }) {
  const section = ((rec.product_screening ?? []) as Screened[]).filter((x) => x.requested_line);
  const best = section.find((x) => x.ai_status === "recommended");
  const others = section.filter((x) => x !== best).sort((x, y) => (x.rank ?? 99) - (y.rank ?? 99));
  const extra = (rec.cross_sell ?? []) as CrossSell[];
  if (others.length === 0 && extra.length === 0) return null;
  return (
    <Panel id="products" icon={<Package className="size-5" />} title={best ? "Why not the others in this section" : "Policies checked in this section"}>
      {others.length > 0 && (
        <ul className="divide-y divide-rule overflow-hidden rounded-xl border border-rule">
          {others.map((x) => {
            const eligible = x.status === "eligible";
            const why = eligible ? x.rationale : x.reasons.slice(0, 2).join(" ");
            return (
              <li key={x.code} className="flex gap-3 p-4">
                {eligible ? <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-muted-ink" aria-hidden /> : <XCircle className="mt-0.5 size-5 shrink-0 text-bad" aria-hidden />}
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-bold text-ink">{x.name}</p>
                    {eligible ? (
                      <Badge tone="gray">
                        {x.fit ? `${human(x.fit)} fit` : "Eligible"}
                        {x.rank ? ` · #${x.rank}` : ""}
                      </Badge>
                    ) : (
                      <Badge tone="red">Not suitable</Badge>
                    )}
                  </div>
                  {why && (
                    <p className="mt-1 text-sm leading-relaxed text-ink-2">
                      {eligible && <span className="font-semibold">Eligible, but a weaker match: </span>}
                      {why}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {extra.length > 0 && (
        <div className={others.length ? "mt-6" : ""}>
          <Eyebrow>Other cover worth a conversation</Eyebrow>
          <ul className="mt-3 space-y-2">
            {extra.map((x) => (
              <li key={x.code} className="flex flex-wrap items-start justify-between gap-2 rounded-xl border border-rule p-4">
                <div className="min-w-0 flex-1">
                  <p className="font-bold text-ink">{x.name ?? x.code}</p>
                  {x.rationale && <p className="mt-1 text-sm leading-relaxed text-ink-2">{x.rationale}</p>}
                </div>
                <Badge tone={x.needs_underwriter ? "amber" : "blue"}>{x.needs_underwriter ? "Needs a risk check" : "Also suits"}</Badge>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  );
}

/* ------------------------------------------------------------------ risk */

const FACTOR: Record<string, string> = {
  age_band: "Age",
  bmi: "BMI",
  smoker: "Smoking",
  sum_insured: "Cover amount",
  prior_claims_3y: "Past claims",
  vehicle_age_years: "Vehicle age",
  vehicle_value: "Vehicle value",
  driving_years: "Driving experience",
  pre_existing_conditions: "Health conditions",
  occupation_risk: "Occupation",
  property_age_years: "Property age",
  annual_income: "Income",
  dependents: "Dependants",
  family_medical_history: "Family history",
};
const factor = (signal: string) => FACTOR[signal] ?? human(signal);

const TONE: Record<string, { text: string; label: string }> = {
  low: { text: "text-ok", label: "Low risk" },
  medium: { text: "text-warn", label: "Medium risk" },
  high: { text: "text-bad", label: "High risk" },
};

/** Why each underwriting rule sends a case to an underwriter, in plain words. */
const WHY_REFER: Record<string, string> = {
  "underwriting.pre_existing": "The customer declared a medical condition. Existing conditions can change how likely a health claim is, so an underwriter decides whether to offer cover and on what terms.",
  "underwriting.serious_condition": "A serious condition (heart disease, cancer or stroke) was declared. These affect life and family cover heavily, so an underwriter must assess it.",
  "underwriting.bmi": "The BMI is 40 or above, which is a higher health risk, so an underwriter must review it.",
  "underwriting.smoker_age": "A smoker aged 50 or over is a higher risk for life and family cover, so an underwriter must review it.",
  "underwriting.occupation": "The customer's job is rated high risk, which can change the cover or price, so an underwriter must review it.",
  "underwriting.cover_vs_income": "The cover asked for is more than 20 times their yearly income. An underwriter has to check that the amount is justified.",
  "underwriting.claims_history": "There were 3 or more claims in the last 3 years, so an underwriter must review the claims record.",
  "underwriting.inexperienced_driver": "The driver has under a year of experience, which raises the risk, so an underwriter must review it.",
  "underwriting.property_age": "The property is over 100 years old, so an underwriter must review it before cover is offered.",
  "underwriting.industry_risk": "The company works in a high-risk industry, so an underwriter must review the scheme.",
  "underwriting.min_age": "The applicant is under 18, so an underwriter must look at the case.",
  "underwriting.vehicle_age": "The vehicle is over 20 years old, so an underwriter must look at the case.",
};

/** An (i) button that says exactly why this case is (or is not) sent to an underwriter. */
function UnderwriterInfo({ refer, referral }: { refer: boolean; referral: { id: string; reason: string }[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        type="button"
        aria-label="Why is an underwriter review needed?"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="grid size-6 place-items-center rounded-full text-muted-ink transition-colors hover:bg-white/70 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
      >
        <Info className="size-4" aria-hidden />
      </button>
      {open && (
        <div role="dialog" className="absolute top-8 right-0 z-20 w-72 rounded-xl border border-rule bg-card p-4 text-left text-xs leading-relaxed font-normal tracking-normal text-ink-2 normal-case shadow-lg">
          <p className="mb-1.5 text-sm font-bold text-ink">{refer ? "Why a review is needed" : "Why no review is needed"}</p>
          {refer ? (
            referral.length > 0 ? (
              <ul className="space-y-2">
                {referral.map((x) => (
                  <li key={x.id}>
                    <strong className="text-ink">{x.reason}</strong>
                    <span className="block">{WHY_REFER[x.id] ?? "A company underwriting rule was triggered."}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p>A company underwriting rule was triggered, so an underwriter must look at it first.</p>
            )
          ) : (
            <p>None of the company&apos;s underwriting rules was triggered by this customer&apos;s answers.</p>
          )}
        </div>
      )}
    </div>
  );
}

function Risk({ rec }: { rec: RecDetail }) {
  const risk = (rec.decisions as Decisions).risk;
  const refer = rec.action === "refer_to_underwriter";
  const tone = TONE[risk?.band ?? ""];
  const score = typeof risk?.score === "number" ? Math.round(risk.score * 100) : null;
  const referral = ((rec.rule_results ?? []) as { id: string; passed: boolean; reason: string }[]).filter((x) => x.id.startsWith("underwriting.") && !x.passed);

  if (!risk) {
    return (
      <Panel id="risk" icon={<ShieldAlert className="size-5" />} title="Risk">
        <p className="text-sm text-muted-ink">Not rated: the rules stopped this case before risk scoring.</p>
      </Panel>
    );
  }
  return (
    <Panel id="risk" icon={<ShieldAlert className="size-5" />} title="Risk" action={<RiskBadge band={risk.band} />}>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-rule p-5">
          <Eyebrow>Risk rating</Eyebrow>
          <p className="mt-2 flex items-baseline gap-2">
            <span className={cx("font-display text-2xl font-bold", tone?.text ?? "text-ink")}>{tone?.label ?? human(risk.band ?? "")}</span>
            {score !== null && <span className="text-sm text-muted-ink">{score} out of 100</span>}
          </p>
          {score !== null && (
            <div className="mt-4">
              <div className="relative h-2.5 rounded-full bg-gradient-to-r from-ok via-[#e0a82e] to-bad">
                <span className="absolute top-1/2 size-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-white bg-ink shadow" style={{ left: `${Math.min(Math.max(score, 3), 97)}%` }} aria-hidden />
              </div>
              <div className="mt-1.5 flex justify-between text-[11px] text-muted-ink">
                <span>Low</span>
                <span>Medium</span>
                <span>High</span>
              </div>
            </div>
          )}
        </div>

        <div className={cx("rounded-xl p-5", refer ? "bg-warn-soft" : "bg-ok-soft")}>
          <div className="flex items-center justify-between gap-2">
            <Eyebrow>Underwriter review</Eyebrow>
            <UnderwriterInfo refer={refer} referral={referral} />
          </div>
          <p className={cx("mt-2 flex items-center gap-2 font-display text-xl font-bold", refer ? "text-warn" : "text-ok")}>
            {refer ? <AlertTriangle className="size-5" aria-hidden /> : <CheckCircle2 className="size-5" aria-hidden />}
            {refer ? "Needed first" : "Not needed"}
          </p>
          <p className="mt-1.5 text-sm leading-relaxed text-ink-2">
            {refer ? "An underwriter must look at this case before anyone contacts the customer." : "No underwriting rule was triggered, so the case can go straight to approval."}
          </p>
          {refer && referral.length > 0 && (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-2">
              {referral.map((x) => (
                <li key={x.id}>{x.reason}</li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {risk.summary && <p className="mt-5 text-[15px] leading-relaxed text-ink">{risk.summary}</p>}

      {risk.reasons?.length ? (
        <div className="mt-5">
          <Eyebrow>What shaped this rating</Eyebrow>
          <ul className="mt-3 grid gap-3 md:grid-cols-2">
            {risk.reasons.slice(0, 4).map((x, i) => (
              <li key={`${x.signal}-${i}`} className="rounded-xl border border-rule p-4">
                <span className="inline-block rounded-full bg-brand-soft px-2.5 py-0.5 text-xs font-bold text-brand">{factor(x.signal)}</span>
                <p className="mt-2 text-sm leading-relaxed text-ink-2">{x.explanation}</p>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Panel>
  );
}

/* ------------------------------------------------------------ next steps */

function NextSteps({ rec }: { rec: RecDetail }) {
  const steps = ((rec.next_steps ?? []) as NextStep[]).filter((s) => s.kind !== "approve" && s.kind !== "collect");
  const fit = (rec.decisions as Record<string, unknown>).product_fit as ProductFit | undefined;
  const talk = (fit?.talking_points ?? []).map((x) => x.explanation);
  return (
    <Panel id="next-steps" icon={<ListChecks className="size-5" />} title="Suggested next actions" action={steps.length > 0 ? <Badge tone="gray">{steps.length} action{steps.length === 1 ? "" : "s"}</Badge> : undefined}>
      {steps.length === 0 ? (
        <p className="text-sm text-muted-ink">No next steps for this case.</p>
      ) : (
        <ol className="space-y-3">
          {steps.map((s, i) => (
            <li key={i} className="flex gap-3 rounded-xl border border-rule p-4">
              <span className={cx("grid size-8 shrink-0 place-items-center rounded-full text-sm font-bold", s.kind === "stop" ? "bg-bad-soft text-bad" : "bg-brand-soft text-brand")}>{i + 1}</span>
              <div className="min-w-0">
                <p className="font-bold text-ink">{s.title}</p>
                <p className="text-xs text-muted-ink">{s.owner}</p>
                {s.detail && <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{s.detail}</p>}
                {s.quote && <p className="mt-2 rounded-lg bg-ice p-2.5 text-sm text-ink">&ldquo;{s.quote}&rdquo;</p>}
              </div>
            </li>
          ))}
        </ol>
      )}
      {talk.length > 0 && (
        <div className="mt-5 space-y-3">
          {talk.length > 0 && <TalkingPoints items={talk} />}
        </div>
      )}
    </Panel>
  );
}

/** The call plan as a short walk-through: numbered, in the order the call would flow. */
function TalkingPoints({ items }: { items: string[] }) {
  return (
    <div className="rounded-xl bg-brand-soft p-4">
      <Eyebrow>Talking points for the call</Eyebrow>
      <p className="mt-1 text-xs text-muted-ink">A suggested way to run the conversation, in order.</p>
      <ol className="mt-3 space-y-3">
        {items.map((t, i) => (
          <li key={i} className="flex gap-3 text-sm leading-6 text-ink">
            <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-brand text-xs font-bold text-white">{i + 1}</span>
            <span>{t}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
