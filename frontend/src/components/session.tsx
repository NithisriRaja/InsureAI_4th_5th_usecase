"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, ApiError, session, SESSION_EVENT, type User } from "@/lib/api";

export const ROLES: { value: string; label: string; hint: string }[] = [
  { value: "sales", label: "Sales & marketing", hint: "Approves direct and broker prospects" },
  { value: "adviser", label: "Adviser", hint: "Approves life and savings prospects" },
  { value: "underwriter", label: "Underwriter", hint: "Approves referrals to underwriting" },
  { value: "admin", label: "Admin", hint: "Can approve every queue" },
];

/** Who may decide each approval queue (mirrors the backend's routing.QUEUE_ROLES). */
export const QUEUE_ROLES: Record<string, string[]> = {
  sales: ["sales", "admin"],
  adviser: ["adviser", "admin"],
  underwriting: ["underwriter", "admin"],
};

/** The app always acts as this user: no sign-in screen. */
const DEFAULT_USER = { name: "Admin", role: "admin" };

// One sign-in at a time, shared by every component that asks for the user.
let signingIn: Promise<string> | null = null;
function autoSignIn(): Promise<string> {
  signingIn ??= api<{ session_id: string }>("/sessions", { method: "POST", body: DEFAULT_USER })
    .then((r) => {
      session.set(r.session_id);
      return r.session_id;
    })
    .finally(() => {
      signingIn = null;
    });
  return signingIn;
}

/** Current user. Signs in as the default admin when there is no session or it has expired. */
export function useUser() {
  const [token, setToken] = useState<string | null>(null);
  useEffect(() => {
    const sync = () => setToken(session.get());
    sync();
    window.addEventListener(SESSION_EVENT, sync);
    window.addEventListener("storage", sync); // other tabs
    return () => {
      window.removeEventListener(SESSION_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  const q = useQuery({
    queryKey: ["me", token],
    queryFn: async () => {
      if (!session.get()) await autoSignIn();
      try {
        return await api<User>("/sessions/me");
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 401)) throw e;
        session.set(null); // expired: start a fresh admin session
        await autoSignIn();
        return await api<User>("/sessions/me");
      }
    },
    staleTime: 60_000,
    retry: 1,
  });
  return { user: q.data ?? null };
}

/** Who the app is acting as (top right). */
export function UserMenu() {
  const { user } = useUser();
  if (!user) return null;
  const roleLabel = ROLES.find((r) => r.value === user.role)?.label ?? user.role;
  return (
    <div className="ml-auto flex items-center gap-2.5 px-2 py-1.5 text-sm">
      <span className="grid size-8 place-items-center rounded-full bg-nav text-xs font-semibold text-white">{initials(user.name)}</span>
      <span className="hidden text-left leading-tight sm:block">
        <span className="block font-medium text-ink">{user.name}</span>
        <span className="block text-xs text-muted">{roleLabel === "Admin" ? "Administrator" : roleLabel}</span>
      </span>
    </div>
  );
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "?") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}
