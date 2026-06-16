"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Calendar, CheckSquare, ClipboardList, GraduationCap, MessageSquare, UserPlus, Users, XCircle } from "lucide-react";
import { StaffLayout, useStaffAuth } from "@/components/StaffLayout";
import { StaffPage } from "@/components/StaffPage";
import { StatCard } from "@/components/StatCard";
import { QuickAction } from "@/components/QuickAction";
import { apiFetch } from "@/lib/api";
import type { DashboardStats, ProximaEscala } from "@/types";

export default function DashboardPage() {
  const { usuario, ready, sair } = useStaffAuth();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [proximas, setProximas] = useState<ProximaEscala[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!ready) return;
    Promise.all([
      apiFetch<DashboardStats>("/dashboard/stats"),
      apiFetch<ProximaEscala[]>("/dashboard/proximas-escalas"),
    ])
      .then(([s, p]) => {
        setStats(s);
        setProximas(p);
      })
      .finally(() => setLoading(false));
  }, [ready]);

  const nome = usuario?.nome?.split(" ")[0] ?? "";

  return (
    <StaffLayout loading={loading}>
      <StaffPage
        title={`Bem-vindo, ${nome}`}
        description="Visão geral do grupo de coroinhas — escalas, formações, presenças e mais."
        onLogout={sair}
      >
        {stats && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4 mb-8">
              <StatCard label="Total de coroinhas" value={stats.total_coroinhas} icon={Users} accent="burgundy" />
              <StatCard label="Ativos" value={stats.ativos} icon={Users} accent="green" />
              <StatCard label="Em formação" value={stats.em_formacao} icon={UserPlus} accent="amber" />
              <StatCard label="Escalas do mês" value={stats.escalas_mes} icon={Calendar} accent="gold" />
              <StatCard label="Faltas do mês" value={stats.faltas_mes} icon={XCircle} accent="red" />
              <StatCard label="Formações realizadas" value={stats.formacoes_realizadas} icon={GraduationCap} accent="burgundy" />
            </div>

            <div className="grid lg:grid-cols-2 gap-6 mb-8">
              <div className="card-liturgical p-6">
                <div className="flex items-center gap-2 mb-4">
                  <Calendar className="size-5 text-gold" aria-hidden />
                  <h2 className="font-display text-xl font-semibold">Próximas escalas</h2>
                </div>
                {proximas.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Nenhuma escala cadastrada.</p>
                ) : (
                  <ul className="space-y-3">
                    {proximas.map((e) => (
                      <li key={e.id} className="flex justify-between items-center text-sm border-b border-border pb-2 last:border-0">
                        <span>
                          {new Date(e.data + "T12:00:00").toLocaleDateString("pt-BR")} · {e.missa}
                        </span>
                        <span className="text-muted-foreground">{e.coroinhas_count} coroinhas</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="space-y-3">
                <h2 className="font-display text-xl font-semibold px-1">Atalhos</h2>
                <QuickAction href="/dashboard/inscricoes" title="Nova inscrição" description="Aprovar cadastros pendentes" icon={UserPlus} />
                <QuickAction href="/dashboard/escalas" title="Montar escala" description="Sortear coroinhas" icon={Calendar} />
                <QuickAction href="/dashboard/presenca" title="Marcar presença" description="Durante a missa" icon={CheckSquare} />
                <QuickAction href="/dashboard/comunicacao" title="Enviar mensagem" description="Avisar o grupo" icon={MessageSquare} />
              </div>
            </div>

            {stats.inscricoes_pendentes > 0 && (
              <div className="card-liturgical p-4 flex items-center gap-4 border-l-4 border-l-gold">
                <ClipboardList className="size-8 text-gold shrink-0" aria-hidden />
                <div className="flex-1">
                  <p className="font-medium">{stats.inscricoes_pendentes} inscrição(ões) aguardando aprovação</p>
                </div>
                <Link href="/dashboard/inscricoes" className="btn-primary text-sm shrink-0">Revisar</Link>
              </div>
            )}
          </>
        )}
      </StaffPage>
    </StaffLayout>
  );
}
