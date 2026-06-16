"use client";

import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import { StaffLayout, useStaffAuth, podeGerenciarCoroinhas } from "@/components/StaffLayout";
import { StaffPage } from "@/components/StaffPage";
import { StatCard } from "@/components/StatCard";
import { BarChart3, Calendar, GraduationCap, Users } from "lucide-react";
import { apiDownload, apiFetch } from "@/lib/api";
import { turmaLabel } from "@/lib/format";
import type { RelatorioGeral } from "@/types";

const MESES = [
  "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

export default function RelatoriosPage() {
  const { ready, sair, usuario } = useStaffAuth();
  const podeExportar = usuario ? podeGerenciarCoroinhas(usuario.tipo_perfil) : false;
  const hoje = new Date();
  const [rel, setRel] = useState<RelatorioGeral | null>(null);
  const [loading, setLoading] = useState(true);
  const [mes, setMes] = useState(hoje.getMonth() + 1);
  const [ano, setAno] = useState(hoje.getFullYear());
  const [exportando, setExportando] = useState(false);
  const [erro, setErro] = useState("");

  useEffect(() => {
    if (!ready) return;
    apiFetch<RelatorioGeral>("/relatorios/geral")
      .then(setRel)
      .finally(() => setLoading(false));
  }, [ready]);

  async function exportarEscala(formato: "pdf" | "csv" = "pdf") {
    setErro("");
    setExportando(true);
    try {
      const ext = formato === "pdf" ? "pdf" : "csv";
      await apiDownload(
        `/relatorios/escala-mes?ano=${ano}&mes=${mes}&formato=${formato}`,
        `escala-${ano}-${String(mes).padStart(2, "0")}.${ext}`,
      );
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Erro ao exportar");
    } finally {
      setExportando(false);
    }
  }

  return (
    <StaffLayout loading={loading}>
      <StaffPage title="Relatórios" description="Indicadores e exportação de escalas." onLogout={sair}>
        {podeExportar && (
          <div className="card-liturgical p-6 mb-8 border-l-4 border-l-gold">
            <h2 className="font-display text-lg font-semibold mb-2 flex items-center gap-2">
              <Calendar className="size-5 text-gold" aria-hidden />
              Exportar escala do mês
            </h2>
            <p className="text-sm text-muted-foreground mb-4">
              PDF com data, missa, horário, função litúrgica e foto de cada coroinha escalado.
            </p>
            <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-end flex-wrap">
              <label className="text-sm">
                <span className="text-muted-foreground text-xs block mb-1">Mês</span>
                <select value={mes} onChange={(e) => setMes(Number(e.target.value))} className="input-field">
                  {MESES.map((nome, i) => (
                    <option key={nome} value={i + 1}>{nome}</option>
                  ))}
                </select>
              </label>
              <label className="text-sm">
                <span className="text-muted-foreground text-xs block mb-1">Ano</span>
                <input
                  type="number"
                  min={2020}
                  max={2100}
                  value={ano}
                  onChange={(e) => setAno(Number(e.target.value))}
                  className="input-field w-28"
                />
              </label>
              <button
                type="button"
                onClick={() => exportarEscala("pdf")}
                disabled={exportando}
                className="btn-primary flex items-center gap-2"
              >
                <Download className="size-4" aria-hidden />
                {exportando ? "Exportando..." : "Baixar PDF"}
              </button>
              <button
                type="button"
                onClick={() => exportarEscala("csv")}
                disabled={exportando}
                className="btn-outline text-sm"
              >
                CSV
              </button>
            </div>
            {erro && <p className="text-sm text-destructive mt-3">{erro}</p>}
          </div>
        )}

        {rel && (
          <>
            <div className="grid sm:grid-cols-3 gap-4 mb-8">
              <StatCard label="Total de escalas" value={rel.total_escalas} icon={Calendar} />
              <StatCard label="Formações realizadas" value={rel.formacoes_realizadas} icon={GraduationCap} accent="gold" />
              <StatCard label="Taxa de presença" value={`${rel.taxa_presenca}%`} icon={BarChart3} accent="green" />
            </div>

            <div className="grid md:grid-cols-2 gap-6 mb-8">
              <div className="card-liturgical p-6">
                <h2 className="font-display text-lg font-semibold mb-4">Coroinhas por status</h2>
                <ul className="space-y-2 text-sm">
                  {Object.entries(rel.por_status).map(([k, v]) => (
                    <li key={k} className="flex justify-between">
                      <span>{k === "EmFormacao" ? "Em formação" : k}</span>
                      <span className="font-medium">{v}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="card-liturgical p-6">
                <h2 className="font-display text-lg font-semibold mb-4">Por turma</h2>
                <ul className="space-y-2 text-sm">
                  {Object.entries(rel.por_turma).map(([k, v]) => (
                    <li key={k} className="flex justify-between">
                      <span>{turmaLabel(k)}</span>
                      <span className="font-medium">{v}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="card-liturgical p-6">
              <h2 className="font-display text-lg font-semibold mb-4 flex items-center gap-2">
                <Users className="size-5 text-gold" aria-hidden /> Top 5 coroinhas mais escalados
              </h2>
              <ol className="space-y-2">
                {rel.top_escalados.map((t, i) => (
                  <li key={t.nome} className="flex justify-between text-sm">
                    <span>{i + 1}. {t.nome}</span>
                    <span className="text-muted-foreground">{t.escalas} escalas</span>
                  </li>
                ))}
                {rel.top_escalados.length === 0 && (
                  <li className="text-muted-foreground text-sm">Sem dados ainda.</li>
                )}
              </ol>
            </div>
          </>
        )}
      </StaffPage>
    </StaffLayout>
  );
}
