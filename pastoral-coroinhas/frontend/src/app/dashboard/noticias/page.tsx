"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Cake, Star, Trash2 } from "lucide-react";
import { CoroinhaAvatar } from "@/components/CoroinhaAvatar";
import { StaffLayout, useStaffAuth, podeGerenciarCoroinhas, ReadOnlyGestorBanner } from "@/components/StaffLayout";
import { StaffPage } from "@/components/StaffPage";
import { apiFetch, asList } from "@/lib/api";
import { turmaLabel } from "@/lib/format";
import type { Aniversariante, Noticia } from "@/types";

export default function NoticiasPage() {
  const { ready, sair, usuario } = useStaffAuth();
  const podeEditar = usuario ? podeGerenciarCoroinhas(usuario.tipo_perfil) : false;
  const [noticias, setNoticias] = useState<Noticia[]>([]);
  const [aniversariantes, setAniversariantes] = useState<Aniversariante[]>([]);
  const [titulo, setTitulo] = useState("");
  const [conteudo, setConteudo] = useState("");
  const [destaque, setDestaque] = useState(false);
  const [loading, setLoading] = useState(true);

  function load() {
    Promise.all([
      apiFetch<{ results?: Noticia[] } | Noticia[]>("/noticias/"),
      apiFetch<Aniversariante[] | { results?: Aniversariante[] }>("/coroinhas/aniversariantes/"),
    ])
      .then(([n, a]) => {
        setNoticias(asList(n));
        setAniversariantes(asList(a));
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (ready) load();
  }, [ready]);

  const ordenadas = useMemo(
    () => [...noticias].sort((a, b) => Number(b.destaque) - Number(a.destaque)),
    [noticias],
  );

  async function publicar(ev: FormEvent) {
    ev.preventDefault();
    await apiFetch("/noticias/", {
      method: "POST",
      body: JSON.stringify({ titulo, conteudo, destaque, ativo: true }),
    });
    setTitulo("");
    setConteudo("");
    setDestaque(false);
    load();
  }

  async function remover(id: number) {
    await apiFetch(`/noticias/${id}/`, { method: "PATCH", body: JSON.stringify({ ativo: false }) });
    load();
  }

  return (
    <StaffLayout loading={loading}>
      <StaffPage title="Canal de Notícias" description="Comunicados para coroinhas e famílias." onLogout={sair}>
        <ReadOnlyGestorBanner tipoPerfil={usuario?.tipo_perfil} />
        {aniversariantes.length > 0 && (
          <div className="card-liturgical p-6 mb-8 border-l-4 border-l-gold">
            <div className="flex items-center gap-2 mb-4">
              <Cake className="size-5 text-gold" aria-hidden />
              <h2 className="font-display text-lg font-semibold">Aniversariantes do mês</h2>
            </div>
            <ul className="grid sm:grid-cols-2 gap-3">
              {aniversariantes.map((a) => (
                <li key={a.id} className="flex items-center gap-3 text-sm">
                  <CoroinhaAvatar nome={a.nome} fotoUrl={a.foto_url} size="md" />
                  <div>
                    <p className="font-medium">{a.nome}</p>
                    <p className="text-muted-foreground text-xs">
                      {String(a.dia).padStart(2, "0")}/{String(new Date().getMonth() + 1).padStart(2, "0")} · {a.idade} anos · {turmaLabel(a.turma)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}

        {podeEditar && (
        <form onSubmit={publicar} className="card-liturgical p-6 mb-8 space-y-4">
          <h2 className="font-display text-lg font-semibold">Nova notícia</h2>
          <input placeholder="Título" value={titulo} onChange={(e) => setTitulo(e.target.value)} className="input-field" required />
          <textarea placeholder="Conteúdo" value={conteudo} onChange={(e) => setConteudo(e.target.value)} className="input-field min-h-[120px]" required />
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" checked={destaque} onChange={(e) => setDestaque(e.target.checked)} className="accent-[var(--burgundy)]" />
            <Star className="size-4 text-gold" aria-hidden />
            Destacar no topo
          </label>
          <button type="submit" className="btn-primary w-fit">Publicar</button>
        </form>
        )}

        <div className="space-y-4">
          {ordenadas.filter((n) => n.ativo).map((n) => (
            <article
              key={n.id}
              className={`card-liturgical p-6 ${n.destaque ? "border-l-4 border-l-gold bg-gold/5" : ""}`}
            >
              <div className="flex justify-between gap-4">
                <div className="flex-1">
                  {n.destaque && (
                    <p className="text-xs uppercase tracking-wide text-gold font-medium mb-1 flex items-center gap-1">
                      <Star className="size-3" aria-hidden /> Destaque
                    </p>
                  )}
                  <h3 className="font-display text-lg font-semibold">{n.titulo}</h3>
                  <p className="text-xs text-muted-foreground mt-1">
                    {new Date(n.publicado_em).toLocaleDateString("pt-BR")}
                    {n.autor_nome ? ` · ${n.autor_nome}` : ""}
                  </p>
                  <p className="text-sm mt-3 whitespace-pre-wrap">{n.conteudo}</p>
                </div>
                {podeEditar && (
                <button
                  type="button"
                  onClick={() => remover(n.id)}
                  className="text-muted-foreground hover:text-destructive shrink-0"
                  aria-label="Remover notícia"
                >
                  <Trash2 className="size-4" />
                </button>
                )}
              </div>
            </article>
          ))}
        </div>
      </StaffPage>
    </StaffLayout>
  );
}
