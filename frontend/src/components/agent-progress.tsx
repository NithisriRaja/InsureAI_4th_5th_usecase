"use client";

import { CheckCircle2, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { cx } from "@/components/ui";

const STEPS = ["Checking consent and customer details", "Assessing the risk", "Matching the best policy", "Writing the reasons and next steps"];

/** Shown while the agents work on a customer. The steps are indicative: they move on a timer and the
 *  last one stays active until the real result arrives. */
export function AgentProgress({ name }: { name?: string | null }) {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 3500);
    return () => clearInterval(t);
  }, []);

  return (
    <div role="status" aria-live="polite" className="rounded-3xl bg-white px-6 py-12 text-center shadow-[0_24px_60px_-20px_rgba(10,17,40,0.45)] sm:px-12">
      <div className="mx-auto grid size-16 place-items-center rounded-full bg-brand-soft">
        <Loader2 className="size-8 animate-spin text-brand" aria-hidden />
      </div>
      <h2 className="mt-6 font-display text-xl font-bold text-ink">{name ? `Our agents are reviewing ${name}'s application` : "Our agents are reviewing the application"}</h2>
      <p className="mx-auto mt-1.5 max-w-sm text-sm text-muted-ink">This usually takes under a minute. Please keep this page open, the result opens by itself.</p>
      <ol className="mx-auto mt-8 max-w-xs space-y-3 text-left text-sm">
        {STEPS.map((label, i) => (
          <li key={label} className={cx("flex items-center gap-3", i > step && "text-faint", i === step && "font-semibold text-ink", i < step && "text-ink-2")}>
            {i < step ? <CheckCircle2 className="size-5 shrink-0 text-ok" aria-hidden /> : i === step ? <Loader2 className="size-5 shrink-0 animate-spin text-brand" aria-hidden /> : <span className="grid size-5 shrink-0 place-items-center" aria-hidden><span className="size-2 rounded-full bg-rule" /></span>}
            {label}
          </li>
        ))}
      </ol>
    </div>
  );
}
