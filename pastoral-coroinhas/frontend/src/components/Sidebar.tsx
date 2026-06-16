"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Church } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { navIcons, type NavIconKey } from "@/lib/nav-icons";

export interface NavItem {
  href: string;
  label: string;
  icon: NavIconKey;
  disabled?: boolean;
}

export interface NavGroup {
  title: string;
  items: NavItem[];
}

interface SidebarProps {
  groups: NavGroup[];
  subtitle?: string;
}

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  const Icon: LucideIcon = navIcons[item.icon];

  if (item.disabled || item.href === "#") {
    return (
      <span
        className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-sidebar-foreground/40 cursor-not-allowed"
        title="Em breve"
      >
        <Icon className="size-4 shrink-0 opacity-50" aria-hidden />
        {item.label}
        <span className="ml-auto text-[10px] uppercase tracking-wide opacity-60">breve</span>
      </span>
    );
  }

  return (
    <Link
      href={item.href}
      className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all ${
        active
          ? "bg-sidebar-accent text-sidebar-primary font-medium shadow-soft border border-sidebar-primary/20"
          : "text-sidebar-foreground/85 hover:bg-sidebar-accent/80 hover:text-sidebar-accent-foreground"
      }`}
      aria-current={active ? "page" : undefined}
    >
      <Icon className={`size-4 shrink-0 ${active ? "text-sidebar-primary" : ""}`} aria-hidden />
      {item.label}
    </Link>
  );
}

export function Sidebar({ groups, subtitle }: SidebarProps) {
  const pathname = usePathname();

  function isActive(href: string) {
    if (href === "#") return false;
    if (href === "/dashboard") return pathname === "/dashboard";
    return pathname === href || pathname.startsWith(`${href}/`);
  }

  return (
    <aside className="w-72 min-h-screen text-sidebar-foreground flex flex-col relative overflow-hidden bg-gradient-hero shrink-0">
      <div className="absolute inset-0 opacity-[0.07] pointer-events-none sidebar-glow" />

      <div className="relative p-6 border-b border-sidebar-border/60 flex items-center gap-3">
        <div
          className="size-12 rounded-full grid place-items-center shadow-lg ring-2 ring-white/10 bg-gradient-gold text-burgundy-deep"
        >
          <Church className="size-6" aria-hidden />
        </div>
        <div className="min-w-0">
          <div className="font-display text-lg font-semibold leading-tight truncate">
            Pastoral dos Coroinhas
          </div>
          <div className="text-xs text-sidebar-foreground/70">Sistema Paroquial</div>
          {subtitle && (
            <div className="text-xs text-gold mt-0.5 truncate" title={subtitle}>
              {subtitle}
            </div>
          )}
        </div>
      </div>

      <nav className="relative flex-1 p-4 space-y-5 overflow-y-auto">
        {groups.map((group) => (
          <div key={group.title}>
            <p className="px-3 mb-1.5 text-[10px] uppercase tracking-widest text-sidebar-foreground/50 font-medium">
              {group.title}
            </p>
            <div className="space-y-0.5">
              {group.items.map((item) => (
                <NavLink key={item.href + item.label} item={item} active={isActive(item.href)} />
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="relative p-4 border-t border-sidebar-border/60 text-xs text-sidebar-foreground/50 italic text-center">
        &ldquo;Servire Deo, regnare est.&rdquo;
      </div>
    </aside>
  );
}

export const dashboardNav: NavGroup[] = [
  {
    title: "Geral",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: "dashboard" },
      { href: "/dashboard/noticias", label: "Notícias", icon: "noticias" },
      { href: "/dashboard/documentos", label: "Documentos", icon: "documentos" },
    ],
  },
  {
    title: "Gestão",
    items: [
      { href: "/dashboard/coroinhas", label: "Coroinhas", icon: "coroinhas" },
      { href: "/dashboard/inscricoes", label: "Inscrições", icon: "inscricao" },
      { href: "/dashboard/escalas", label: "Escalas", icon: "escalas" },
      { href: "/dashboard/presenca", label: "Presença", icon: "presenca" },
      { href: "/dashboard/formacao", label: "Formação", icon: "formacao" },
    ],
  },
  {
    title: "Famílias",
    items: [
      { href: "/portal", label: "Portal dos Pais", icon: "portal" },
      { href: "/dashboard/comunicacao", label: "Comunicação", icon: "comunicacao" },
      { href: "/dashboard/relatorios", label: "Relatórios", icon: "relatorios" },
    ],
  },
];

export const portalNav: NavGroup[] = [
  {
    title: "Portal",
    items: [{ href: "/portal", label: "Início", icon: "portal" }],
  },
];
