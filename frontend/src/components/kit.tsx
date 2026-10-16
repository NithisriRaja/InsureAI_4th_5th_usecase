"use client";

import { type LucideIcon, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type CSSProperties, type MouseEvent, type ReactNode, useState } from "react";
import { initials } from "@/components/session";
import { Badge, Card, cx, type Tone } from "@/components/ui";
import type { LeadOut } from "@/lib/api";

// ------------------------------------------------------------------- layout ---

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0 flex-1">
        <h1 className="font-display text-2xl font-bold text-ink">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted-ink">{subtitle}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </header>
  );
}

/** A titled card; `pad={false}` for tables that run edge to edge. */
export function Panel({ title, action, children, className, pad = true }: { title: string; action?: ReactNode; children: ReactNode; className?: string; pad?: boolean }) {
  return (
    <Card className={cx("p-0", className)}>
      <div className="flex items-center justify-between gap-3 px-5 pt-4">
        <h2 className="font-display text-base font-bold text-ink">{title}</h2>
        {action}
      </div>
      <div className={pad ? "p-5" : "pt-3"}>{children}</div>
    </Card>
  );
}

/** A section of the customer page, reachable from the header's "on this page" links. */
export function Section({ id, icon, title, action, children }: { id: string; icon: ReactNode; title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-20 rounded-xl border border-rule bg-card p-5 shadow-card">
      <header className="mb-4 flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 font-display text-base font-bold text-ink">
          <span className="text-brand">{icon}</span>
          {title}
        </h2>
        {action}
      </header>
      {children}
    </section>
  );
}

/** Label / value rows. */
export function Facts({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="divide-y divide-rule text-sm">
      {rows.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-3 py-2">
          <dt className="text-muted-ink">{k}</dt>
          <dd className="text-right font-semibold break-words text-ink">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

// -------------------------------------------------------------------- tiles ---

const ICON_TONE: Record<Tone, string> = {
  gray: "bg-ice-2 text-ink-2",
  green: "bg-ok-soft text-ok",
  amber: "bg-warn-soft text-warn",
  red: "bg-bad-soft text-bad",
  blue: "bg-info-soft text-info",
  brand: "bg-brand-soft text-brand",
};

export function Stat({ icon: Icon, label, value, sub, tone = "brand" }: { icon: LucideIcon; label: string; value: ReactNode; sub?: string; tone?: Tone }) {
  return (
    <Card className="flex items-start justify-between gap-3 p-5">
      <div className="min-w-0">
        <p className="text-sm font-medium text-muted-ink">{label}</p>
        <p className="mt-2 font-display text-3xl font-bold tracking-tight text-ink">{value}</p>
        {sub && <p className="mt-1 truncate text-xs text-muted-ink">{sub}</p>}
      </div>
      <span className={cx("grid size-10 shrink-0 place-items-center rounded-lg", ICON_TONE[tone])}>
        <Icon className="size-5" aria-hidden />
      </span>
    </Card>
  );
}

export function Avatar({ name, size = 8 }: { name: string; size?: 8 | 10 | 14 }) {
  const dim = { 8: "size-8 text-xs", 10: "size-10 text-sm", 14: "size-14 text-lg" }[size];
  return (
    <span aria-hidden className={cx("grid shrink-0 place-items-center rounded-full bg-brand-soft font-bold text-brand", dim)}>
      {initials(name || "?")}
    </span>
  );
}

// ------------------------------------------------------------------- tables ---

/** A table row that opens ``href`` when clicked anywhere. Buttons and links inside keep their own
 * action; keyboard and screen-reader users use the row's own link (the customer's name). */
export function RowLink({ href, children, className }: { href: string; children: ReactNode; className?: string }) {
  const router = useRouter();
  const open = (e: MouseEvent<HTMLTableRowElement>) => {
    if ((e.target as HTMLElement).closest("a, button, input, select, textarea")) return;
    if (window.getSelection()?.toString()) return; // selecting text, not navigating
    if (e.ctrlKey || e.metaKey || e.button === 1) window.open(href, "_blank");
    else router.push(href);
  };
  return (
    <tr onClick={open} onAuxClick={(e) => e.button === 1 && open(e)} className={cx("cursor-pointer transition-colors hover:bg-ice", className)}>
      {children}
    </tr>
  );
}

export function Td({ children, className }: { children?: ReactNode; className?: string }) {
  return <td className={cx("px-4 py-3 align-middle text-ink-2", className)}>{children}</td>;
}

/** Plain table: the wrapper scrolls sideways on small screens. */
export function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-left text-sm">
        <thead>
          <tr className="border-b border-rule text-xs font-semibold tracking-wide text-muted-ink uppercase">
            {head.map((h, i) => (
              <th key={`${h}-${i}`} className="px-4 py-3 font-semibold whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-rule">{children}</tbody>
      </table>
    </div>
  );
}

/** First column of every customer table: bold name (the row's link) and one quiet line. */
export function CustomerCell({ lead, sub, href }: { lead: LeadOut; sub?: string | null; href?: string }) {
  return (
    <Td>
      <Link href={href ?? `/customers/${lead.id}`} className="font-semibold text-ink hover:text-brand">
        {lead.name || "Unnamed customer"}
      </Link>
      {sub && <span className="block text-xs whitespace-nowrap text-muted-ink">{sub}</span>}
    </Td>
  );
}

export function ViewLink({ href, children = "View" }: { href: string; children?: ReactNode }) {
  return (
    <Link href={href} className="font-semibold whitespace-nowrap text-brand hover:underline">
      {children}
    </Link>
  );
}

export function Tabs<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: { value: T; label: string; count?: number }[] }) {
  return (
    <div role="tablist" className="flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button
          key={o.value}
          role="tab"
          aria-selected={value === o.value}
          onClick={() => onChange(o.value)}
          className={cx(
            "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors",
            value === o.value ? "bg-brand text-white" : "border border-rule bg-card text-ink-2 hover:bg-ice",
          )}
        >
          {o.label}
          {o.count !== undefined && (
            <span className={cx("rounded-full px-1.5 text-xs", value === o.value ? "bg-white/20 text-white" : "bg-ice-2 text-muted-ink")}>{o.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

export function SearchBox({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <label className="relative w-full sm:w-64">
      <Search className="absolute top-2.5 left-3 size-4 text-faint" aria-hidden />
      <input
        className="h-9 w-full rounded-lg border border-rule-2 bg-card pr-3 pl-9 text-sm text-ink placeholder:text-faint focus:border-brand focus:outline-none"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label="Search"
      />
    </label>
  );
}

export function Pagination({ total, limit, offset, onChange }: { total: number; limit: number; offset: number; onChange: (offset: number) => void }) {
  if (total <= limit) return null;
  const pages = Math.ceil(total / limit);
  const page = Math.floor(offset / limit) + 1;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-rule px-4 py-3 text-sm text-muted-ink">
      <span>
        Showing {offset + 1}-{Math.min(offset + limit, total)} of {total}
      </span>
      <div className="flex items-center gap-1">
        {Array.from({ length: pages }, (_, i) => i + 1).map((p) => (
          <button
            key={p}
            onClick={() => onChange((p - 1) * limit)}
            aria-current={p === page ? "page" : undefined}
            className={cx("size-8 rounded-lg text-sm font-semibold", p === page ? "bg-brand text-white" : "text-ink-2 hover:bg-ice")}
          >
            {p}
          </button>
        ))}
      </div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="px-5 py-10 text-center text-sm text-muted-ink">{children}</p>;
}

// ------------------------------------------------------------------- charts ---

// Chart colours for risk: the theme's ordinal blue ramp (darker = riskier), always labelled.
export const RISK_COLOR: Record<string, string> = { low: "var(--viz-ord-1)", medium: "var(--viz-ord-2)", high: "var(--viz-ord-3)", none: "var(--rule-2)" };

/** Small floating label used by the charts on hover. */
function Tip({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div className="pointer-events-none absolute z-10 -translate-x-1/2 rounded-lg border border-rule bg-card px-3 py-2 text-xs whitespace-nowrap shadow-raised" style={style}>
      {children}
    </div>
  );
}

const plural = (n: number) => `${n} ${n === 1 ? "customer" : "customers"}`;

export function Donut({ parts, centre }: { parts: { label: string; n: number; color: string }[]; centre: string }) {
  const [hover, setHover] = useState<string | null>(null);
  const total = parts.reduce((a, p) => a + p.n, 0);
  const r = 52;
  const c = 2 * Math.PI * r;
  const gap = parts.filter((p) => p.n > 0).length > 1 ? 1.5 : 0; // white gap between slices
  const active = parts.find((p) => p.label === hover);
  const share = (n: number) => (total ? Math.round((n / total) * 100) : 0);
  let offset = 0;
  return (
    <div className="flex w-full flex-wrap items-center justify-center gap-x-8 gap-y-4">
      <div className="relative shrink-0">
        <svg viewBox="0 0 120 120" className="size-40" role="img" aria-label={parts.map((p) => `${p.label}: ${p.n}`).join(", ")}>
          <circle cx="60" cy="60" r={r} fill="none" stroke="var(--viz-track)" strokeWidth="14" />
          {total > 0 &&
            parts
              .filter((p) => p.n > 0)
              .map((p) => {
                const len = (p.n / total) * c;
                const dash = Math.max(0, len - gap);
                const el = (
                  <circle
                    key={p.label}
                    cx="60"
                    cy="60"
                    r={r}
                    fill="none"
                    stroke={p.color}
                    strokeWidth={hover === p.label ? 18 : 14}
                    strokeDasharray={`${dash} ${c - dash}`}
                    strokeDashoffset={-offset}
                    transform="rotate(-90 60 60)"
                    className="cursor-pointer transition-[stroke-width]"
                    opacity={hover && hover !== p.label ? 0.45 : 1}
                    onMouseEnter={() => setHover(p.label)}
                    onMouseLeave={() => setHover(null)}
                  />
                );
                offset += len;
                return el;
              })}
          <text x="60" y="60" textAnchor="middle" fontSize="22" fontWeight="700" fill="var(--ink)">
            {active ? active.n : total}
          </text>
          <text x="60" y="76" textAnchor="middle" fontSize="9" fill="var(--muted-ink)">
            {active ? active.label : centre}
          </text>
        </svg>
        {active && (
          <Tip style={{ left: "50%", top: -8 }}>
            <p className="font-semibold text-ink">{active.label}</p>
            <p className="text-ink-2">
              {plural(active.n)} · {share(active.n)}%
            </p>
          </Tip>
        )}
      </div>
      <ul className="min-w-[170px] space-y-1 text-sm">
        {parts.map((p) => (
          <li
            key={p.label}
            onMouseEnter={() => setHover(p.label)}
            onMouseLeave={() => setHover(null)}
            className={cx("flex cursor-default items-center justify-between gap-3 rounded-md px-2 py-1.5", hover === p.label && "bg-ice")}
          >
            <span className="flex items-center gap-2 text-ink-2">
              <span className="size-2.5 rounded-full" style={{ background: p.color }} />
              {p.label}
            </span>
            <span className="font-semibold text-ink tabular-nums">{p.n}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Vertical columns with gridlines; the count sits on top of each column, details on hover. */
export function ColumnChart({ rows, height = 200 }: { rows: { label: string; n: number; color?: string }[]; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...rows.map((r) => r.n));
  const step = Math.max(1, Math.ceil(max / 4));
  const top = step * 4;
  const total = rows.reduce((a, r) => a + r.n, 0);
  return (
    <div className="flex gap-2" role="img" aria-label={rows.map((r) => `${r.label}: ${r.n}`).join(", ")}>
      <div className="flex flex-col justify-between pb-10 text-right text-[11px] text-muted-ink tabular-nums" style={{ height: height + 40 }}>
        {[4, 3, 2, 1, 0].map((k) => (
          <span key={k} className="-translate-y-1.5 leading-none">
            {k * step}
          </span>
        ))}
      </div>
      <div className="relative min-w-0 flex-1">
        <div className="pointer-events-none absolute inset-x-0 top-0 flex flex-col justify-between" style={{ height }}>
          {[0, 1, 2, 3, 4].map((k) => (
            <span key={k} className="border-t border-rule" />
          ))}
        </div>
        <div className="relative flex items-end justify-around gap-3" style={{ height }}>
          {rows.map((r, i) => (
            <div
              key={r.label}
              className="relative flex h-full max-w-16 flex-1 cursor-pointer flex-col items-center justify-end"
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            >
              {hover === i && (
                <Tip style={{ left: "50%", bottom: `calc(${(r.n / top) * 100}% + 28px)` }}>
                  <p className="font-semibold text-ink">{r.label}</p>
                  <p className="text-ink-2">
                    {plural(r.n)}
                    {total ? ` · ${Math.round((r.n / total) * 100)}%` : ""}
                  </p>
                </Tip>
              )}
              <span className="mb-1 text-sm font-semibold text-ink tabular-nums">{r.n}</span>
              <span
                className="w-full rounded-t-md transition-opacity"
                style={{ height: `${(r.n / top) * 100}%`, background: r.color ?? "var(--viz-1)", minHeight: r.n ? 4 : 0, opacity: hover !== null && hover !== i ? 0.45 : 1 }}
              />
            </div>
          ))}
        </div>
        <div className="flex justify-around gap-3 pt-2">
          {rows.map((r) => (
            <span key={r.label} className="h-8 max-w-24 flex-1 text-center text-xs leading-tight text-ink-2">
              {r.label}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Half-circle gauge: `value` out of `max`. */
export function Gauge({ value, max, label, color = "var(--viz-ord-2)" }: { value: number; max: number; label: string; color?: string }) {
  const [hover, setHover] = useState(false);
  const len = Math.PI * 60;
  const pct = max ? Math.min(1, value / max) : 0;
  return (
    <div className="relative" onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      <svg viewBox="0 0 160 96" className="h-auto w-48" role="img" aria-label={`${label}: ${value} of ${max}`}>
        <path d="M20 84 A60 60 0 0 1 140 84" fill="none" stroke="var(--viz-track)" strokeWidth={14} strokeLinecap="round" />
        <path d="M20 84 A60 60 0 0 1 140 84" fill="none" stroke={color} strokeWidth={14} strokeLinecap="round" strokeDasharray={`${pct * len} ${len}`} />
        <text x={80} y={72} textAnchor="middle" fontSize={26} fontWeight={700} fill="var(--ink)">
          {value}
        </text>
        <text x={80} y={90} textAnchor="middle" fontSize={10} fill="var(--muted-ink)">
          {label}
        </text>
      </svg>
      {hover && (
        <Tip style={{ left: "50%", top: -12 }}>
          <p className="font-semibold text-ink">
            {value} of {max} {label}
          </p>
          <p className="text-ink-2">{Math.round(pct * 100)}% of assessed customers</p>
        </Tip>
      )}
    </div>
  );
}

export function RiskBadge({ band }: { band: string | null | undefined }) {
  if (!band) return <span className="text-xs text-muted-ink">Not rated</span>;
  const tone: Tone = band === "low" ? "green" : band === "medium" ? "amber" : "red";
  return <Badge tone={tone}>{band.charAt(0).toUpperCase() + band.slice(1)}</Badge>;
}
