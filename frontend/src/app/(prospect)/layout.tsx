import { AppShell } from "@/components/shell";
import { Providers } from "./providers";

/** New customers (use case 4): /dashboard, /prospects, /risk, /products, /priorities, /engagement, /customers. */
export default function ProspectLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="area-prospect">
      <Providers>
        <AppShell>{children}</AppShell>
      </Providers>
    </div>
  );
}
