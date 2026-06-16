"use client";

import { FormEvent, useEffect, useState } from "react";
import { Cake, Send } from "lucide-react";
import { CoroinhaAvatar } from "@/components/CoroinhaAvatar";
import { StaffLayout, useStaffAuth, podeGerenciarCoroinhas, ReadOnlyGestorBanner } from "@/components/StaffLayout";
import { StaffPage } from "@/components/StaffPage";
import { apiFetch, asList } from "@/lib/api";
import type { Aniversariante, Coroinha, Escala, Mensagem, ProximaEscala } from "@/types";

const TEXTO_PARABENS =
  "Parabéns, {nome}! Feliz {idade} anos! Que Deus abençoe sua vida e seu serviço no altar.";

export default function ComunicacaoPage() {
  const { ready, sair, usuario } = useStaffAuth();
  const podeEditar = usuario ? podeGerenciarCoroinhas(usuario.tipo_perfil) : false;
  const [coroinhas, setCoroinhas] = useState<Coroinha[]>([]);
  const [historico, setHistorico] = useState<Mensagem[]>([]);
  const [selecionados, setSelecionados] = useState<number[]>([]);
  const [canal, setCanal] = useState("WhatsApp");
  const [corpo, setCorpo] = useState("Olá {nome}, você está escalado para servir na missa {escala}.");
  const [loading, setLoading] = useState(true);

  function load() {
    Promise.all([
      apiFetch<{ results?: Coroinha[] } | Coroinha[]>("/coroinhas/"),
      apiFetch<{ results?: Mensagem[] } | Mensagem[]>("/mensagens/"),
    ]).then(([c, m]) => {
      setCoroinhas(asList(c));
      setHistorico(asList(m));
    }).finally(() => setLoading(false));
  }

  useEffect(() => {
    if (ready) load();
  }, [ready]);

  function toggle(id: number) {
    setSelecionados((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  }

  function selecionarTodos() {
    setSelecionados(coroinhas.map((c) => c.id));
  }

  async function selecionarEscalados() {
    const proximas = await apiFetch<ProximaEscala[]>("/dashboard/proximas-escalas");
    if (proximas.length === 0) return;
    const escala = await apiFetch<Escala>(`/escalas/${proximas[0].id}/`);
    setSelecionados(escala.itens.map((i) => i.coroinha_id));
  }

  async function selecionarAniversariantes() {
    const lista = await apiFetch<Aniversariante[] | { results?: Aniversariante[] }>("/coroinhas/aniversariantes/");
    const items = asList(lista);
    setSelecionados(items.map((a) => a.id));
    setCorpo(TEXTO_PARABENS);
  }

  async function enviar(ev: FormEvent) {
    ev.preventDefault();
    await apiFetch("/mensagens/enviar", {
      method: "POST",
      body: JSON.stringify({ canal, corpo, coroinha_ids: selecionados }),
    });
    setSelecionados([]);
    load();
  }

  return (
    <StaffLayout loading={loading}>
      <StaffPage title="Comunicação" description="Avisos por WhatsApp ou e-mail (simulação)." onLogout={sair}>
        <ReadOnlyGestorBanner tipoPerfil={usuario?.tipo_perfil} />
        {podeEditar && (
        <form onSubmit={enviar} className="card-liturgical p-6 mb-8 space-y-4">
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={selecionarTodos} className="btn-outline text-sm">Todos</button>
            <button type="button" onClick={selecionarEscalados} className="btn-outline text-sm">Escalados</button>
            <button type="button" onClick={selecionarAniversariantes} className="btn-outline text-sm flex items-center gap-1">
              <Cake className="size-4" aria-hidden /> Aniversariantes
            </button>
            <button type="button" onClick={() => setSelecionados([])} className="btn-outline text-sm">Limpar</button>
            <span className="text-sm text-muted-foreground self-center">Destinatários ({selecionados.length})</span>
          </div>
          <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto">
            {coroinhas.map((c) => (
              <label key={c.id} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm cursor-pointer border ${selecionados.includes(c.id) ? "bg-primary text-primary-foreground border-primary" : "border-border"}`}>
                <input type="checkbox" className="sr-only" checked={selecionados.includes(c.id)} onChange={() => toggle(c.id)} />
                <CoroinhaAvatar nome={c.nome} fotoUrl={c.foto_url} size="sm" />
                {c.nome}
              </label>
            ))}
          </div>
          <select value={canal} onChange={(e) => setCanal(e.target.value)} className="input-field max-w-xs">
            <option value="WhatsApp">WhatsApp</option>
            <option value="Email">E-mail</option>
          </select>
          <textarea
            value={corpo}
            onChange={(e) => setCorpo(e.target.value)}
            className="input-field min-h-[100px]"
            placeholder="Use {nome}, {escala} e {idade}"
          />
          <button type="submit" disabled={selecionados.length === 0} className="btn-primary">
            <Send className="size-4" aria-hidden /> Enviar
          </button>
        </form>
        )}

        <div className="card-liturgical p-6">
          <h2 className="font-display text-lg font-semibold mb-4">Histórico de mensagens</h2>
          {historico.length === 0 ? (
            <p className="text-muted-foreground text-sm">Nenhuma mensagem enviada ainda.</p>
          ) : (
            <ul className="space-y-3">
              {historico.map((m) => (
                <li key={m.id} className="border-b border-border pb-3 text-sm">
                  <p className="font-medium">{m.canal} · {new Date(m.enviada_em).toLocaleString("pt-BR")}</p>
                  <p className="text-muted-foreground mt-1">{m.corpo}</p>
                  <p className="text-xs mt-1">Para: {m.destinatarios_nomes.join(", ")}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </StaffPage>
    </StaffLayout>
  );
}
