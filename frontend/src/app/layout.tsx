import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AppShell } from "@/components/layout/app-shell";
import { getCurrentUserSafe } from "@/lib/api/auth";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "Prospect AI",
    template: "%s · Prospect AI",
  },
  description:
    "Dashboard de prospecção comercial: descoberta, auditoria digital e priorização de oportunidades.",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // `getCurrentUserSafe` nunca lança — em `/login`/`/register` (sem cookie
  // de sessão ainda) simplesmente resolve `null`, e o AppShell renderiza um
  // layout sem a barra lateral autenticada nessas rotas (ver app-shell.tsx).
  const user = await getCurrentUserSafe();

  return (
    <html
      lang="pt-BR"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <TooltipProvider delay={200}>
          <AppShell user={user}>{children}</AppShell>
        </TooltipProvider>
      </body>
    </html>
  );
}
