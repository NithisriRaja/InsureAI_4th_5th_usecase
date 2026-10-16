import type { Metadata } from "next";
import { Geist_Mono, Inter, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const jakarta = Plus_Jakarta_Sans({ variable: "--font-jakarta", subsets: ["latin"], weight: ["600", "700", "800"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "InsureAI · New Customers & Renewals",
  description: "AI prospecting, risk checks and product matching, plus policy renewals, retention and personalised offers, with human approval",
};

// Each half of the app has its own providers and sidebar shell: (prospect)/layout.tsx and renewal/layout.tsx.
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} ${jakarta.variable} ${geistMono.variable} min-h-screen font-sans antialiased`}>{children}</body>
    </html>
  );
}
