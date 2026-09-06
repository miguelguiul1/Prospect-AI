import type { LucideIcon } from "lucide-react";
import { LayoutDashboard, Building2, Search, Settings } from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

/** Itens mínimos pedidos pela Fase 5. Nenhuma seção de F6+ (CRM, Prototype
 * Builder) aparece aqui — ver docs/dashboard.md. */
export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/prospects", label: "Prospects", icon: Building2 },
  { href: "/pesquisas", label: "Pesquisas", icon: Search },
  { href: "/configuracoes", label: "Configurações", icon: Settings },
];
