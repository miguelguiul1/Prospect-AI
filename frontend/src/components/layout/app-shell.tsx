"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, Radar, Plus, LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { SidebarNav } from "@/components/layout/sidebar-nav";
import { logoutAction } from "@/lib/auth/actions";
import type { UserResponse } from "@/lib/api/types";

function Wordmark() {
  return (
    <Link href="/dashboard" className="flex items-center gap-2 px-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring rounded-md">
      <span className="flex size-7 items-center justify-center rounded-md bg-sidebar-primary text-sidebar-primary-foreground">
        <Radar aria-hidden className="size-4" />
      </span>
      <span className="font-heading text-base font-semibold tracking-tight text-sidebar-foreground">
        Prospect AI
      </span>
    </Link>
  );
}

const AUTH_ROUTES = ["/login", "/register"];

export function AppShell({ children, user }: { children: ReactNode; user: UserResponse | null }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();

  // `/login`/`/register` renderizam sem a barra lateral/topbar autenticada
  // — mostrar navegação para rotas protegidas antes de haver sessão seria
  // enganoso (o middleware já bloquearia o clique de qualquer forma).
  if (AUTH_ROUTES.some((route) => pathname === route || pathname.startsWith(`${route}/`))) {
    return <>{children}</>;
  }

  return (
    <div className="flex min-h-screen w-full bg-background">
      {/* Sidebar — desktop */}
      <aside className="hidden w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar lg:flex">
        <div className="flex h-14 items-center border-b border-sidebar-border px-4">
          <Wordmark />
        </div>
        <div className="flex-1 overflow-y-auto">
          <SidebarNav />
        </div>
        <div className="border-t border-sidebar-border px-4 py-3 text-xs text-sidebar-foreground/60">
          Fase 7 · CRM
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Topbar */}
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-border bg-background px-4">
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetTrigger
              render={
                <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Abrir menu de navegação">
                  <Menu className="size-5" />
                </Button>
              }
            />
            <SheetContent side="left" className="w-64 bg-sidebar p-0 text-sidebar-foreground">
              <SheetTitle className="sr-only">Menu de navegação</SheetTitle>
              <div className="flex h-14 items-center border-b border-sidebar-border px-4">
                <Wordmark />
              </div>
              <SidebarNav onNavigate={() => setMobileOpen(false)} />
            </SheetContent>
          </Sheet>

          <span className="font-heading text-sm font-medium text-foreground lg:hidden">
            Prospect AI
          </span>

          <div className="ml-auto flex items-center gap-2">
            <Button size="sm" render={<Link href="/pesquisas/nova" />}>
              <Plus className="size-4" />
              Nova pesquisa
            </Button>
            {user ? (
              <div className="flex items-center gap-2 border-l border-border pl-2">
                <span className="hidden max-w-[14ch] truncate text-xs text-muted-foreground sm:inline" title={user.email}>
                  {user.name}
                </span>
                <form action={logoutAction}>
                  <Button type="submit" size="icon" variant="ghost" aria-label="Sair">
                    <LogOut className="size-4" />
                  </Button>
                </form>
              </div>
            ) : null}
          </div>
        </header>

        <main className="min-w-0 flex-1 overflow-x-hidden px-4 py-6 sm:px-6 lg:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}
