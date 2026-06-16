"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { ExternalLink, Filter } from "lucide-react";
import { StaffLayout, useStaffAuth, podeGerenciarCoroinhas, ReadOnlyGestorBanner } from "@/components/StaffLayout";
import { StaffPage } from "@/components/StaffPage";
import { apiFetch, asList } from "@/lib/api";
import { categoriaDocumentoLabel } from "@/lib/format";
import type { Documento } from "@/types";

const CATEGORIAS = ["", "Liturgia", "Formacao", "Ritual", "Outro"];

export default function DocumentosPage() {
  const { ready, sair, usuario } = useStaffAuth();
  const podeEditar = usuario ? podeGerenciarCoroinhas(usuario.tipo_perfil) : false;
  const [docs, setDocs] = useState<Documento[]>([]);
  const [titulo, setTitulo] = useState("");
  const [descricao, setDescricao] = useState("");
  const [url, setUrl] = useState("");
  const [categoria, setCategoria] = useState("Formacao");
  const [filtro, setFiltro] = useState("");
  const [loading, setLoading] = useState(true);

  function load() {
    const qs = filtro ? `?categoria=${filtro}` : "";
    apiFetch<{ results?: Documento[] } | Documento[]>(`/documentos/${qs}`)
      .then((d) => setDocs(asList(d)))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (ready) load();
  }, [ready, filtro]);

  const filtrados = useMemo(() => docs.filter((d) => d.ativo), [docs]);

  async function adicionar(ev: FormEvent) {
    ev.preventDefault();
    await apiFetch("/documentos/", {
      method: "POST",
      body: JSON.stringify({ titulo, descricao, url, categoria, ativo: true }),
    });
    setTitulo("");
    setDescricao("");
    setUrl("");
    load();
  }

  return (
    <StaffLayout loading={loading}>
      <StaffPage
        title="Documentos & Anexos"
        description="Conteúdos de formação, rituais, paramentos e materiais."
        onLogout={sair}
      >
        <ReadOnlyGestorBanner tipoPerfil={usuario?.tipo_perfil} />
        {podeEditar && (
        <form onSubmit={adicionar} className="card-liturgical p-6 mb-8 space-y-4">
          <h2 className="font-display text-lg font-semibold">Novo documento</h2>
          <input placeholder="Título" value={titulo} onChange={(e) => setTitulo(e.target.value)} className="input-field" required />
          <select value={categoria} onChange={(e) => setCategoria(e.target.value)} className="input-field">
            {CATEGORIAS.filter(Boolean).map((c) => (
              <option key={c} value={c}>{categoriaDocumentoLabel(c)}</option>
            ))}
          </select>
          <input placeholder="URL do documento" value={url} onChange={(e) => setUrl(e.target.value)} className="input-field" type="url" />
          <textarea placeholder="Descrição" value={descricao} onChange={(e) => setDescricao(e.target.value)} className="input-field" />
          <button type="submit" className="btn-primary w-fit">Adicionar documento</button>
        </form>
        )}

        <div className="relative max-w-xs mb-6">
          <Filter className="absolute left-3 top-1/2 z-10 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" aria-hidden />
          <select value={filtro} onChange={(e) => setFiltro(e.target.value)} className="input-field input-field--icon-left appearance-none">
            <option value="">Todas as categorias</option>
            {CATEGORIAS.filter(Boolean).map((c) => (
              <option key={c} value={c}>{categoriaDocumentoLabel(c)}</option>
            ))}
          </select>
        </div>

        <div className="grid sm:grid-cols-2 gap-4">
          {filtrados.map((d) => (
            <div key={d.id} className="card-liturgical p-5">
              <p className="text-xs text-muted-foreground uppercase tracking-wide">{categoriaDocumentoLabel(d.categoria)}</p>
              <h3 className="font-semibold mt-1">{d.titulo}</h3>
              {d.descricao && <p className="text-sm text-muted-foreground mt-1">{d.descricao}</p>}
              {d.url ? (
                <a href={d.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm text-burgundy mt-3 hover:underline">
                  Ler conteúdo <ExternalLink className="size-3.5" aria-hidden />
                </a>
              ) : (
                <span className="text-sm text-muted-foreground mt-3 inline-block">Sem link</span>
              )}
            </div>
          ))}
        </div>
      </StaffPage>
    </StaffLayout>
  );
}
