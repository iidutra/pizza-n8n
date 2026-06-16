"use client";

import { FormEvent, Fragment, useEffect, useState } from "react";
import { Calendar, Pencil, Plus, Shuffle, Trash2, UserCog } from "lucide-react";
import { CoroinhaAvatar } from "@/components/CoroinhaAvatar";
import { FuncoesEscalaForm } from "@/components/FuncoesEscalaForm";
import { StaffLayout, useStaffAuth, podeGerenciarCoroinhas, ReadOnlyGestorBanner } from "@/components/StaffLayout";
import { StaffPage } from "@/components/StaffPage";
import { apiFetch, asList, mediaUrl } from "@/lib/api";
import {
  funcoesFromItens,
  funcoesParaPayload,
  funcoesVazias,
} from "@/lib/scheduling";
import type { Coroinha, Escala, Missa } from "@/types";

const DIAS_SEMANA = [
  "Domingo", "Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado",
];

type TipoRecorrencia = "semanal" | "mensal";

function formatarHorario(horario: string) {
  return horario?.slice(0, 5) ?? "";
}

function labelRecorrencia(m: Missa) {
  if (m.recorrencia) return m.recorrencia;
  if (m.dia_mes) return `Dia ${m.dia_mes} do mês`;
  return m.dia_semana ?? "";
}

export default function EscalasPage() {
  const { ready, sair, usuario } = useStaffAuth();
  const podeEditar = usuario ? podeGerenciarCoroinhas(usuario.tipo_perfil) : false;
  const [missas, setMissas] = useState<Missa[]>([]);
  const [escalas, setEscalas] = useState<Escala[]>([]);
  const [coroinhas, setCoroinhas] = useState<Coroinha[]>([]);
  const [data, setData] = useState("");
  const [missaId, setMissaId] = useState("");
  const [modo, setModo] = useState<"SorteioAutomatico" | "SelecaoManual">("SorteioAutomatico");
  const [quantidade, setQuantidade] = useState(3);
  const [selecionados, setSelecionados] = useState<number[]>([]);
  const [erro, setErro] = useState("");
  const [loading, setLoading] = useState(true);
  const [mostrarFormMissa, setMostrarFormMissa] = useState(false);
  const [editandoMissaId, setEditandoMissaId] = useState<number | null>(null);
  const [nomeMissa, setNomeMissa] = useState("");
  const [tipoRecorrencia, setTipoRecorrencia] = useState<TipoRecorrencia>("semanal");
  const [diaMissa, setDiaMissa] = useState("Domingo");
  const [diaMesMissa, setDiaMesMissa] = useState(13);
  const [horarioMissa, setHorarioMissa] = useState("18:30");
  const [funcoesMontar, setFuncoesMontar] = useState(funcoesVazias);
  const [editandoFuncoesId, setEditandoFuncoesId] = useState<number | null>(null);
  const [funcoesEdicao, setFuncoesEdicao] = useState(funcoesVazias);

  function load() {
    Promise.all([
      apiFetch<Missa[] | { results?: Missa[] }>("/missas/"),
      apiFetch<{ results?: Escala[] } | Escala[]>("/escalas/"),
      apiFetch<{ results?: Coroinha[] } | Coroinha[]>("/coroinhas/"),
    ])
      .then(([m, e, c]) => {
        setMissas(asList(m));
        setEscalas(asList(e));
        setCoroinhas(asList(c));
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (ready) load();
  }, [ready]);

  function resetFormMissa() {
    setNomeMissa("");
    setTipoRecorrencia("semanal");
    setDiaMissa("Domingo");
    setDiaMesMissa(13);
    setHorarioMissa("18:30");
    setEditandoMissaId(null);
    setMostrarFormMissa(false);
  }

  function abrirEdicao(m: Missa) {
    setEditandoMissaId(m.id);
    setNomeMissa(m.nome);
    setTipoRecorrencia(m.dia_mes ? "mensal" : "semanal");
    setDiaMissa(m.dia_semana ?? "Domingo");
    setDiaMesMissa(m.dia_mes ?? 13);
    setHorarioMissa(formatarHorario(m.horario));
    setMostrarFormMissa(true);
  }

  function payloadMissa() {
    return {
      nome: nomeMissa,
      dia_semana: tipoRecorrencia === "semanal" ? diaMissa : null,
      dia_mes: tipoRecorrencia === "mensal" ? diaMesMissa : null,
      horario: horarioMissa,
      ativa: true,
    };
  }

  async function salvarMissa(ev: FormEvent) {
    ev.preventDefault();
    setErro("");
    try {
      if (editandoMissaId) {
        await apiFetch(`/missas/${editandoMissaId}/`, {
          method: "PATCH",
          body: JSON.stringify(payloadMissa()),
        });
      } else {
        await apiFetch("/missas/", {
          method: "POST",
          body: JSON.stringify(payloadMissa()),
        });
      }
      resetFormMissa();
      load();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Erro ao salvar missa");
    }
  }

  async function removerMissa(id: number) {
    if (!confirm("Desativar esta missa?")) return;
    setErro("");
    try {
      await apiFetch(`/missas/${id}/`, { method: "PATCH", body: JSON.stringify({ ativa: false }) });
      load();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Erro ao remover missa");
    }
  }

  async function montarEscala(ev: FormEvent) {
    ev.preventDefault();
    setErro("");
    try {
      await apiFetch("/escalas/montar/", {
        method: "POST",
        body: JSON.stringify({
          data,
          missa_id: Number(missaId),
          modo,
          quantidade,
          coroinha_ids: modo === "SelecaoManual" ? selecionados : undefined,
          funcoes: funcoesParaPayload(funcoesMontar),
        }),
      });
      setFuncoesMontar(funcoesVazias());
      load();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Erro ao montar escala");
    }
  }

  function toggleCoroinha(id: number) {
    setSelecionados((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  function abrirEdicaoFuncoes(escala: Escala) {
    setEditandoFuncoesId(escala.id);
    setFuncoesEdicao(funcoesFromItens(escala.itens));
  }

  async function salvarFuncoes(escalaId: number) {
    setErro("");
    try {
      await apiFetch(`/escalas/${escalaId}/funcoes/`, {
        method: "PATCH",
        body: JSON.stringify({ funcoes: funcoesParaPayload(funcoesEdicao) }),
      });
      setEditandoFuncoesId(null);
      load();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Erro ao salvar funções");
    }
  }

  const missasAtivas = missas.filter((m) => m.ativa);

  return (
    <StaffLayout loading={loading}>
      <StaffPage title="Escalas" description="Cadastro de missas e montagem das escalas." onLogout={sair}>
        {!podeEditar && <ReadOnlyGestorBanner tipoPerfil={usuario?.tipo_perfil} />}
        {erro && (
          <p className="mb-4 text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-4 py-3" role="alert">
            {erro}
          </p>
        )}

        <div className="grid lg:grid-cols-2 gap-6 mb-8">
          <div className="card-liturgical p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-lg font-semibold flex items-center gap-2">
                <Calendar className="size-5 text-gold" aria-hidden /> Missas cadastradas
              </h2>
              {podeEditar && (
                <button
                  type="button"
                  onClick={() => {
                    if (mostrarFormMissa && !editandoMissaId) {
                      resetFormMissa();
                    } else {
                      resetFormMissa();
                      setMostrarFormMissa(true);
                    }
                  }}
                  className="btn-outline text-sm flex items-center gap-1"
                >
                  <Plus className="size-4" aria-hidden />
                  Adicionar
                </button>
              )}
            </div>

            {podeEditar && mostrarFormMissa && (
              <form onSubmit={salvarMissa} className="mb-4 p-4 rounded-lg border border-border space-y-3">
                <input
                  placeholder="Nome (ex: Domingo 18h30)"
                  value={nomeMissa}
                  onChange={(e) => setNomeMissa(e.target.value)}
                  className="input-field"
                  required
                />
                <select
                  value={tipoRecorrencia}
                  onChange={(e) => setTipoRecorrencia(e.target.value as TipoRecorrencia)}
                  className="input-field"
                >
                  <option value="semanal">Toda semana (dia fixo)</option>
                  <option value="mensal">Todo mês (dia fixo)</option>
                </select>
                {tipoRecorrencia === "semanal" ? (
                  <select value={diaMissa} onChange={(e) => setDiaMissa(e.target.value)} className="input-field">
                    {DIAS_SEMANA.map((d) => (
                      <option key={d} value={d}>{d}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="number"
                    min={1}
                    max={31}
                    value={diaMesMissa}
                    onChange={(e) => setDiaMesMissa(Number(e.target.value))}
                    className="input-field"
                    placeholder="Dia do mês (ex: 13)"
                    required
                  />
                )}
                <input
                  type="time"
                  value={horarioMissa}
                  onChange={(e) => setHorarioMissa(e.target.value)}
                  className="input-field"
                  required
                />
                <div className="flex gap-2">
                  <button type="submit" className="btn-primary text-sm">
                    {editandoMissaId ? "Atualizar missa" : "Salvar missa"}
                  </button>
                  <button type="button" onClick={resetFormMissa} className="btn-outline text-sm">
                    Cancelar
                  </button>
                </div>
              </form>
            )}

            <ul className="space-y-2 text-sm">
              {missasAtivas.map((m) => (
                <li key={m.id} className="flex items-center justify-between gap-2 border-b border-border pb-2">
                  <div>
                    <span className="font-medium">{m.nome}</span>
                    <span className="text-muted-foreground block text-xs">
                      {labelRecorrencia(m)} · {formatarHorario(m.horario)}
                    </span>
                  </div>
                  {podeEditar && (
                    <div className="flex gap-1 shrink-0">
                      <button
                        type="button"
                        onClick={() => abrirEdicao(m)}
                        className="p-1.5 rounded hover:bg-muted text-muted-foreground"
                        title="Editar"
                      >
                        <Pencil className="size-4" aria-hidden />
                      </button>
                      <button
                        type="button"
                        onClick={() => removerMissa(m.id)}
                        className="p-1.5 rounded hover:bg-destructive/10 text-destructive"
                        title="Desativar"
                      >
                        <Trash2 className="size-4" aria-hidden />
                      </button>
                    </div>
                  )}
                </li>
              ))}
              {missasAtivas.length === 0 && (
                <li className="text-muted-foreground py-4 text-center">Nenhuma missa cadastrada.</li>
              )}
            </ul>
          </div>

          {podeEditar ? (
            <form onSubmit={montarEscala} className="card-liturgical p-6 space-y-4">
              <h2 className="font-display text-lg font-semibold flex items-center gap-2">
                <Shuffle className="size-5 text-gold" aria-hidden /> Nova escala
              </h2>
              <input type="date" value={data} onChange={(e) => setData(e.target.value)} className="input-field" required />
              <select value={missaId} onChange={(e) => setMissaId(e.target.value)} className="input-field" required>
                <option value="">Selecione a missa...</option>
                {missasAtivas.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.nome} ({labelRecorrencia(m)} · {formatarHorario(m.horario)})
                  </option>
                ))}
              </select>
              <select value={modo} onChange={(e) => setModo(e.target.value as typeof modo)} className="input-field">
                <option value="SorteioAutomatico">Sorteio automático</option>
                <option value="SelecaoManual">Seleção manual</option>
              </select>
              <input
                type="number"
                min={1}
                max={20}
                value={quantidade}
                onChange={(e) => setQuantidade(Number(e.target.value))}
                className="input-field"
                placeholder="Quantidade de coroinhas"
              />
              {modo === "SorteioAutomatico" && (
                <p className="text-xs text-muted-foreground">
                  O sistema distribui de forma equilibrada, evitando repetir o mesmo coroinha.
                </p>
              )}
              {modo === "SelecaoManual" && (
                <div className="max-h-40 overflow-y-auto border border-border rounded-lg p-2 space-y-1">
                  {coroinhas.map((c) => (
                    <label key={c.id} className="flex items-center gap-2 text-sm cursor-pointer">
                      <input
                        type="checkbox"
                        checked={selecionados.includes(c.id)}
                        onChange={() => toggleCoroinha(c.id)}
                      />
                      {c.nome}
                    </label>
                  ))}
                </div>
              )}
              <FuncoesEscalaForm
                coroinhas={coroinhas}
                valores={funcoesMontar}
                onChange={setFuncoesMontar}
              />
              <button type="submit" className="btn-primary w-full">Sortear coroinhas</button>
            </form>
          ) : (
            <div className="card-liturgical p-6 text-sm text-muted-foreground">
              A montagem de escalas é feita pelo coordenador ou secretário.
            </div>
          )}
        </div>

        <div className="card-liturgical overflow-hidden">
          <div className="px-6 py-4 border-b border-border">
            <h2 className="font-display text-xl font-semibold">Escalas montadas</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="table-liturgical">
              <thead>
                <tr>
                  <th>Data</th>
                  <th>Missa</th>
                  <th>Coroinhas e funções</th>
                  {podeEditar && <th className="w-28" />}
                </tr>
              </thead>
              <tbody>
                {escalas.map((e) => (
                  <Fragment key={e.id}>
                    <tr>
                      <td>{new Date(e.data + "T12:00:00").toLocaleDateString("pt-BR")}</td>
                      <td>{e.missa_nome}</td>
                      <td>
                        <div className="flex flex-wrap gap-2">
                          {e.itens.map((i) => (
                            <div
                              key={i.id}
                              className="flex items-center gap-1.5 rounded-full border border-border px-2 py-1"
                              title={i.funcao_label ? `${i.funcao_label}: ${i.coroinha_nome}` : i.coroinha_nome}
                            >
                              <CoroinhaAvatar
                                nome={i.coroinha_nome}
                                fotoUrl={mediaUrl(i.coroinha_foto_url)}
                                size="sm"
                              />
                              <span className="text-sm">
                                {i.funcao_label ? (
                                  <>
                                    <span className="text-gold font-medium">{i.funcao_label}</span>
                                    <span className="text-muted-foreground"> · {i.coroinha_nome}</span>
                                  </>
                                ) : (
                                  i.coroinha_nome
                                )}
                              </span>
                            </div>
                          ))}
                        </div>
                      </td>
                      {podeEditar && (
                        <td>
                          <button
                            type="button"
                            onClick={() =>
                              editandoFuncoesId === e.id
                                ? setEditandoFuncoesId(null)
                                : abrirEdicaoFuncoes(e)
                            }
                            className="btn-outline text-xs flex items-center gap-1 whitespace-nowrap"
                          >
                            <UserCog className="size-3.5" aria-hidden />
                            Funções
                          </button>
                        </td>
                      )}
                    </tr>
                    {editandoFuncoesId === e.id && (
                      <tr key={`${e.id}-funcoes`}>
                        <td colSpan={podeEditar ? 4 : 3} className="bg-muted/20 p-4">
                          <FuncoesEscalaForm
                            coroinhas={coroinhas}
                            valores={funcoesEdicao}
                            onChange={setFuncoesEdicao}
                            compact
                          />
                          <div className="flex gap-2 mt-3">
                            <button
                              type="button"
                              onClick={() => salvarFuncoes(e.id)}
                              className="btn-primary text-sm"
                            >
                              Salvar funções
                            </button>
                            <button
                              type="button"
                              onClick={() => setEditandoFuncoesId(null)}
                              className="btn-outline text-sm"
                            >
                              Cancelar
                            </button>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
                {escalas.length === 0 && (
                  <tr>
                    <td colSpan={podeEditar ? 4 : 3} className="text-center py-8 text-muted-foreground">
                      Nenhuma escala montada.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </StaffPage>
    </StaffLayout>
  );
}
