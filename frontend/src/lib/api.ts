import type { components } from "./api-types";

type S = components["schemas"];
export type LeadOut = S["LeadOut"];
export type LeadDetail = S["LeadDetail"];
export type RecBrief = S["RecBrief"];
export type RecDetail = S["RecDetail"];
export type RunOut = S["RunOut"];
export type BatchOut = S["BatchOut"];
export type Page<T> = { items: T[]; total: number; limit: number; offset: number };

/* Free-form JSON blocks on RecDetail, typed for what this UI reads. */
export type Reason = { signal: string; explanation: string };
export type ScoreDecision = { band?: string; score?: number; confidence?: string; reasons?: Reason[]; summary?: string };
export type RankedProduct = { code: string; name?: string; fit?: string; rationale?: string };
export type CrossSell = {
  code: string;
  name?: string;
  line?: string;
  rationale?: string;
  reasons?: Reason[];
  sold_through?: string;
  needs_underwriter?: boolean;
  description?: string;
};
export type Screened = {
  code: string;
  name: string;
  line: string;
  requested_line: boolean;
  status: "eligible" | "not_suitable" | "not_assessed";
  reasons: string[];
  evidence: string[];
  ai_status: "recommended" | "ranked" | "also_suits" | null;
  rank?: number;
  fit?: string;
  rationale?: string;
  needs_underwriter?: boolean;
};
export type Approachability = { score: number | null; band: string | null; label: string; reason: string };
export type NextStep = { title: string; detail: string; owner: string; kind: string; done: boolean; items?: string[]; quote?: string | null };
export type RuleResult = { id: string; passed: boolean; severity: string; reason: string };
export type Checklist = {
  completeness_pct?: number;
  evidence_required?: { item: string }[];
};
export type Justification = { headline?: string; summary?: string; approver_items?: { title: string; detail: string }[] };
export type Approval = { decision: string; actor: string; role: string; reason?: string | null; edits?: Record<string, unknown>; at: string };
export type User = { id: string; name: string; role: string };

// The combined backend (../main.py) serves this app's API under /prospect.
export const API_URL = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/prospect`;

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

const SESSION_KEY = "insights.session";
export const SESSION_EVENT = "insights-session";

/** Session token from POST /sessions; sent as X-Session-Id (approvals need it). */
export const session = {
  get(): string | null {
    try {
      return localStorage.getItem(SESSION_KEY);
    } catch {
      return null;
    }
  },
  set(token: string | null) {
    try {
      if (token) localStorage.setItem(SESSION_KEY, token);
      else localStorage.removeItem(SESSION_KEY);
    } catch {
      /* storage unavailable: the session lasts for this page only */
    }
    window.dispatchEvent(new Event(SESSION_EVENT));
  },
};

export async function api<T>(path: string, opts: { method?: string; query?: Query; body?: unknown } = {}): Promise<T> {
  const url = new URL(API_URL + path);
  for (const [k, v] of Object.entries(opts.query ?? {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }
  const headers: Record<string, string> = {};
  if (opts.body !== undefined) headers["content-type"] = "application/json";
  const token = session.get();
  if (token) headers["X-Session-Id"] = token;
  let res: Response;
  try {
    res = await fetch(url, {
      method: opts.method ?? "GET",
      headers,
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    });
  } catch {
    throw new ApiError(0, "network", `Can't reach the backend at ${API_URL}. Is it running?`);
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const e = data?.error;
    // A 422 says which field was refused; show it so the problem can be found.
    const why = Array.isArray(e?.details) ? e.details.slice(0, 2).map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join("; ") : "";
    throw new ApiError(res.status, e?.code ?? "error", `${e?.message ?? `Request failed (${res.status})`}${why ? ` (${why})` : ""}`);
  }
  return data as T;
}

export const ACTIVE_RUN = ["queued", "running"];
