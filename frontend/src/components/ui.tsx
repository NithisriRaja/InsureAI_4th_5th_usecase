"use client";

import { AlertTriangle, Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

export type Tone = "gray" | "green" | "amber" | "red" | "blue" | "brand";

const TONE: Record<Tone, string> = {
  gray: "bg-ice-2 text-ink-2",
  green: "bg-ok-soft text-ok",
  amber: "bg-warn-soft text-warn",
  red: "bg-bad-soft text-bad",
  blue: "bg-info-soft text-info",
  brand: "bg-brand-soft text-brand",
};
export function Badge({ tone = "gray", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold whitespace-nowrap", TONE[tone], className)}>
      {children}
    </span>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  // A caller's own padding (p-0, p-4...) replaces the default instead of fighting it.
  const ownPadding = /(^|\s)p-\d/.test(className ?? "");
  return <section className={cx("rounded-xl border border-rule bg-card shadow-card", !ownPadding && "p-5", className)}>{children}</section>;
}

export function CardTitle({ icon, children, hint }: { icon?: ReactNode; children: ReactNode; hint?: ReactNode }) {
  return (
    <h2 className="mb-4 flex flex-wrap items-baseline gap-x-2 gap-y-1 font-display text-base font-bold text-ink">
      <span className="flex items-center gap-2 self-center">
        {icon}
        {children}
      </span>
      {hint && <span className="text-xs font-normal text-muted">{hint}</span>}
    </h2>
  );
}

export function Button({
  children,
  variant = "primary",
  busy,
  className,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost"; busy?: boolean }) {
  return (
    <button
      {...rest}
      disabled={busy || rest.disabled}
      className={cx(
        "inline-flex h-9 items-center justify-center gap-1.5 rounded-lg px-4 text-sm font-semibold whitespace-nowrap transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" ? "bg-brand text-white hover:bg-brand-hover" : "border border-rule bg-card text-ink hover:bg-ice",
        className,
      )}
    >
      {busy && <Loader2 className="size-3.5 animate-spin" />}
      {children}
    </button>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  return (
    <div role="alert" className="flex items-start gap-2 rounded-lg bg-bad-soft p-4 text-sm text-bad">
      <AlertTriangle className="mt-0.5 size-4 shrink-0" />
      <span>{error instanceof Error ? error.message : "Something went wrong."}</span>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded-xl bg-ice-2", className)} />;
}

/* --------------------------------------------------- bands → tones/labels */

export const ACTION_TONE: Record<string, Tone> = {
  contact_and_quote: "green",
  nurture: "blue",
  refer_to_underwriter: "amber",
  request_info: "amber",
  do_not_contact: "red",
};
