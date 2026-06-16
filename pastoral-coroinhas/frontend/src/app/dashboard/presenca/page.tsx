"use client";

import { useEffect, useState } from "react";
import { StaffLayout, useStaffAuth, podeGerenciarCoroinhas, ReadOnlyGestorBanner } from "@/components/StaffLayout";
import { StaffPage } from "@/components/StaffPage";
import { apiFetch } from "@/lib/api";
import type { Escala, PresencaResumoRow } from "@/types";

interface PresencaEscalaData {
  escala_id: number;
  data: string;
  missa: string;
  itens: { item_id: number; coroinha_id: number; coroinha_nome: string; status: string | null }[];
}

export default function PresencaPage() {
  const { ready, sair, usuario } = useStaffAuth();
  const podeEditar = usuario ? podeGerenciarCoroinhas(usuario.tipo_perfil) : false;
  const [escalas, setEscalas] = useState<Escala[]>([]);
  const [escalaId, setEscalaId] = useState("");
  const [detalhe, setDetalhe] = useState<PresencaEscalaData | null>(null);
  const [resumo, setResumo] = useState<PresencaResumoRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!ready) return;
    Promise.all([
      apiFetch<{ results?: Escala[] } | Escala[]>("/escalas/"),
      apiFetch<PresencaResumoRow[]>("/presenca/resumo"),
    ]).then(([e, r]) => {
      setEscalas(Array.isArray(e) ? e : (e.results ?? []));
      setResumo(r);
    }).finally(() => setLoading(false));
  }, [ready]);

  async function carregarEscala(id: string) {
    setEscalaId(id);
    if (!id) {
      setDetalhe(null);
      return;
    }
    const d = await apiFetch<PresencaEscalaData>(`/presenca/escalas/${id}`);
    setDetalhe(d);
  }

  async function marcar(itemId: number, status: "Presente" | "Ausente") {
    await apiFetch(`/presenca/escalas/${escalaId}`, {
      method: "PATCH",
      body: JSON.stringify({ item_id: itemId, status }),
    });
    carregarEscala(escalaId);
    const r = await apiFetch<PresencaResumoRow[]>("/presenca/resumo");
    setResumo(r);
  }

  return (
    <StaffLayout loading={loading}>
      <StaffPage title="Controle de Presença" description="Marque presença ou falta durante a missa." onLogout={sair}>
        <ReadOnlyGestorBanner tipoPerfil={usuario?.tipo_perfil} />
        <div className="card-liturgical p-6 mb-6">
          <label className="block text-sm font-medium mb-2">Selecione a escala</label>
          <select value={escalaId} onChange={(e) => carregarEscala(e.target.value)} className="input-field max-w-md">
            <option value="">Selecione...</option>
            {escalas.map((e) => (
              <option key={e.id} value={e.id}>
                {new Date(e.data + "T12:00:00").toLocaleDateString("pt-BR")} — {e.missa_nome}
              </option>
            ))}
          </select>
        </div>

        {detalhe && (
          <div className="card-liturgical p-6 mb-8 space-y-4">
            <h2 className="font-display text-lg font-semibold">{detalhe.missa}</h2>
            {detalhe.itens.map((item) => (
              <div key={item.item_id} className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-3">
                <span className="font-medium">{item.coroinha_nome}</span>
                {podeEditar ? (
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => marcar(item.item_id, "Presente")}
                    className={`px-3 py-1.5 rounded-lg text-sm ${item.status === "Presente" ? "bg-emerald-100 text-emerald-800 font-medium" : "btn-outline"}`}
                  >
                    Presente
                  </button>
                  <button
                    type="button"
                    onClick={() => marcar(item.item_id, "Ausente")}
                    className={`px-3 py-1.5 rounded-lg text-sm ${item.status === "Ausente" ? "bg-red-100 text-red-800 font-medium" : "btn-outline"}`}
                  >
                    Ausente
                  </button>
                </div>
                ) : (
                  <span className="text-sm text-muted-foreground">
                    {item.status === "Presente" ? "Presente" : item.status === "Ausente" ? "Ausente" : "Não registrado"}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}

        <div className="card-liturgical overflow-hidden">
          <div className="px-6 py-4 border-b border-border">
            <h2 className="font-display text-xl font-semibold">Resumo por coroinha</h2>
          </div>
          <table className="table-liturgical">
            <thead>
              <tr>
                <th>Coroinha</th>
                <th>Escalas</th>
                <th>Presenças</th>
                <th>Faltas</th>
                <th>% Presença</th>
              </tr>
            </thead>
            <tbody>
              {resumo.map((r) => (
                <tr key={r.coroinha_id}>
                  <td>{r.nome}</td>
                  <td>{r.escalas}</td>
                  <td>{r.presencas}</td>
                  <td>{r.faltas}</td>
                  <td>{r.percentual != null ? `${r.percentual}%` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </StaffPage>
    </StaffLayout>
  );
}
