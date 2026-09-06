import type { LucideIcon } from "lucide-react";
import { LayoutDashboard, Building2, Search, LayoutTemplate, Settings } from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

/** Itens mínimos pedidos pelas Fases 5 e 6. Nenhuma seção de F7+ (CRM,
 * geração de código, publicação) aparece aqui — ver docs/dashboard.md e
 * docs/prototype-builder.md. */
export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/prospects", label: "Prospects", icon: Building2 },
  { href: "/pesquisas", label: "Pesquisas", icon: Search },
  { href: "/prototypes", label: "Protótipos", icon: LayoutTemplate },
  { href: "/configuracoes", label: "Configurações", icon: Settings },
];
