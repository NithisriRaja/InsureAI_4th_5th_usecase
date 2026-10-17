import type { NAV_GROUPS } from "@/nav";

/** Heading above each group of tabs in the sidebar (new customers, renewals). */
export function NavHeading({ group, first }: { group: (typeof NAV_GROUPS)[number]; first?: boolean }) {
  return (
    <p className={`flex items-center gap-2 px-3 pb-2 text-[11px] font-bold tracking-[0.12em] text-nav-glow/80 uppercase ${first ? "" : "mt-4 border-t border-white/10 pt-4"}`}>
      <span className={`size-1.5 rounded-full ${group.tone}`} aria-hidden />
      {group.title}
    </p>
  );
}
