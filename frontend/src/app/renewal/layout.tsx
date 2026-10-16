import { Providers } from "@/renewal/components/providers";
import { AppShell } from "@/renewal/components/shell";

/** Renewals & retention (use case 5): everything under /renewal. */
export default function RenewalLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="area-renewal">
      <Providers>
        <AppShell>{children}</AppShell>
      </Providers>
    </div>
  );
}
