import type { LucideIcon } from "lucide-react";
import {
  BarChart3,
  Calendar,
  CheckSquare,
  ClipboardList,
  FileText,
  GraduationCap,
  Home,
  LayoutDashboard,
  LogOut,
  MessageSquare,
  Newspaper,
  Users,
} from "lucide-react";

export const navIcons = {
  dashboard: LayoutDashboard,
  noticias: Newspaper,
  documentos: FileText,
  coroinhas: Users,
  inscricao: ClipboardList,
  escalas: Calendar,
  presenca: CheckSquare,
  formacao: GraduationCap,
  portal: Home,
  comunicacao: MessageSquare,
  relatorios: BarChart3,
  logout: LogOut,
} satisfies Record<string, LucideIcon>;

export type NavIconKey = keyof typeof navIcons;
