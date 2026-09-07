import type { LucideIcon } from "lucide-react";
import { LayoutDashboard, Building2, Search, LayoutTemplate, Settings, Handshake } from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

/** Itens pedidos pelas Fases 5, 6 e 7 (CRM). Geração de código/publicação
 * ainda não existem — ver docs/dashboard.md e docs/prototype-builder.md. */
export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/prospects", label: "Prospects", icon: Building2 },
  { href: "/crm", label: "CRM", icon: Handshake },
  { href: "/pesquisas", label: "Pesquisas", icon: Search },
  { href: "/prototypes", label: "Protótipos", icon: LayoutTemplate },
  { href: "/configuracoes", label: "Configurações", icon: Settings },
];
