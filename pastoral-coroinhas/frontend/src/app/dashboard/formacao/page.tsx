"use client";

import { FormEvent, useEffect, useState } from "react";
import { StaffLayout, useStaffAuth, podeGerenciarCoroinhas, ReadOnlyGestorBanner } from "@/components/StaffLayout";
import { StaffPage } from "@/components/StaffPage";
import { apiFetch } from "@/lib/api";
import type { Formacao, FormacaoConclusaoRow } from "@/types";

export default function FormacaoPage() {
  const { ready, sair, usuario } = useStaffAuth();
  const podeEditar = usuario ? podeGerenciarCoroinhas(usuario.tipo_perfil) : false;
  const [formacoes, setFormacoes] = useState<Formacao[]>([]);
  const [titulo, setTitulo] = useState("");
  const [data, setData] = useState("");
  const [descricao, setDescricao] = useState("");
  const [expandida, setExpandida] = useState<number | null>(null);
  const [conclusoes, setConclusoes] = useState<FormacaoConclusaoRow[]>([]);
  const [loading, setLoading] = useState(true);

  function loadFormacoes() {
    apiFetch<{ results?: Formacao[] } | Formacao[]>("/formacoes/")
      .then((f) => setFormacoes(Array.isArray(f) ? f : (f.results ?? [])))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (ready) loadFormacoes();
  }, [ready]);

  async function criar(ev: FormEvent) {
    ev.preventDefault();
    await apiFetch("/formacoes/", {
      method: "POST",
      body: JSON.stringify({ titulo, data, descricao }),
    });
    setTitulo("");
    setData("");
    setDescricao("");
    loadFormacoes();
  }

  async function expandir(id: number) {
    setExpandida(id);
    const rows = await apiFetch<FormacaoConclusaoRow[]>(`/formacoes/${id}/conclusoes/`);
    setConclusoes(rows);
  }

  async function toggle(formacaoId: number, coroinhaId: number, concluido: boolean) {
    await apiFetch(`/formacoes/${formacaoId}/toggle_conclusao/`, {
      method: "POST",
      body: JSON.stringify({ coroinha_id: coroinhaId, concluido: !concluido }),
    });
    expandir(formacaoId);
    loadFormacoes();
  }

  return (
    <StaffLayout loading={loading}>
      <StaffPage title="Formações" description="Encontros formativos e controle de conclusão." onLogout={sair}>
        <ReadOnlyGestorBanner tipoPerfil={usuario?.tipo_perfil} />
        {podeEditar && (
        <form onSubmit={criar} className="card-liturgical p-6 mb-8 grid sm:grid-cols-2 gap-4">
          <h2 className="font-display text-lg font-semibold sm:col-span-2">Nova formação</h2>
          <input placeholder="Título" value={titulo} onChange={(e) => setTitulo(e.target.value)} className="input-field" required />
          <input type="date" value={data} onChange={(e) => setData(e.target.value)} className="input-field" required />
          <textarea placeholder="Descrição" value={descricao} onChange={(e) => setDescricao(e.target.value)} className="input-field sm:col-span-2 min-h-[80px]" />
          <button type="submit" className="btn-primary sm:col-span-2 w-fit">Cadastrar formação</button>
        </form>
        )}

        <div className="space-y-4">
          {formacoes.map((f) => (
            <div key={f.id} className="card-liturgical p-6">
              <button type="button" onClick={() => expandir(f.id)} className="w-full text-left">
                <h3 className="font-display text-lg font-semibold">{f.titulo}</h3>
                <p className="text-sm text-muted-foreground">
                  {new Date(f.data + "T12:00:00").toLocaleDateString("pt-BR")} · {f.concluintes_count} concluinte(s)
                </p>
                {f.descricao && <p className="text-sm mt-2">{f.descricao}</p>}
              </button>
              {expandida === f.id && (
                <div className="mt-4 grid sm:grid-cols-2 gap-2 border-t border-border pt-4">
                  {conclusoes.map((c) => (
                    <label key={c.coroinha_id} className={`flex items-center gap-2 text-sm ${podeEditar ? "cursor-pointer" : ""}`}>
                      <input
                        type="checkbox"
                        checked={c.concluido}
                        disabled={!podeEditar}
                        onChange={() => podeEditar && toggle(f.id, c.coroinha_id, c.concluido)}
                      />
                      {c.coroinha_nome}
                    </label>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </StaffPage>
    </StaffLayout>
  );
}
