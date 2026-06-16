"use client";

import { useEffect, useMemo, useState } from "react";
import { Filter, Search, Upload, Users } from "lucide-react";
import { CoroinhaAvatar } from "@/components/CoroinhaAvatar";
import { StaffLayout, useStaffAuth, podeGerenciarCoroinhas, ReadOnlyGestorBanner } from "@/components/StaffLayout";
import { StaffPage } from "@/components/StaffPage";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState } from "@/components/EmptyState";
import { apiFetch, apiFetchForm, asList, mediaUrl } from "@/lib/api";
import { turmaLabel } from "@/lib/format";
import type { Coroinha } from "@/types";

export default function CoroinhasPage() {
  const { ready, sair, usuario } = useStaffAuth();
  const podeEnviarFoto = usuario ? podeGerenciarCoroinhas(usuario.tipo_perfil) : false;
  const [coroinhas, setCoroinhas] = useState<Coroinha[]>([]);
  const [busca, setBusca] = useState("");
  const [statusFiltro, setStatusFiltro] = useState("");
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState("");
  const [enviandoFotoId, setEnviandoFotoId] = useState<number | null>(null);

  useEffect(() => {
    if (!ready) return;
    apiFetch<{ results?: Coroinha[] } | Coroinha[]>("/coroinhas/")
      .then((c) => setCoroinhas(asList(c)))
      .finally(() => setLoading(false));
  }, [ready]);

  const filtrados = useMemo(() => {
    return coroinhas.filter((c) => {
      const matchBusca = c.nome.toLowerCase().includes(busca.toLowerCase());
      const matchStatus = !statusFiltro || c.status === statusFiltro;
      return matchBusca && matchStatus;
    });
  }, [coroinhas, busca, statusFiltro]);

  async function enviarFoto(id: number, file: File) {
    setErro("");
    setEnviandoFotoId(id);
    try {
      const fd = new FormData();
      fd.append("foto", file);
      await apiFetchForm(`/coroinhas/${id}/foto/`, fd);
      const c = await apiFetch<{ results?: Coroinha[] } | Coroinha[]>("/coroinhas/");
      setCoroinhas(asList(c));
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao enviar foto.");
    } finally {
      setEnviandoFotoId(null);
    }
  }

  return (
    <StaffLayout loading={loading}>
      <StaffPage title="Coroinhas" description="Lista completa do grupo paroquial." onLogout={sair}>
        {erro && (
          <p className="mb-4 text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-4 py-3" role="alert">
            {erro}
          </p>
        )}
        {!podeEnviarFoto && <ReadOnlyGestorBanner tipoPerfil={usuario?.tipo_perfil} />}
        <div className="card-liturgical overflow-hidden">
          <div className="px-4 md:px-6 py-4 border-b border-border flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 z-10 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" aria-hidden />
              <input
                type="search"
                placeholder="Buscar por nome..."
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                className="input-field input-field--icon-left"
              />
            </div>
            <div className="relative sm:w-48">
              <Filter className="absolute left-3 top-1/2 z-10 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" aria-hidden />
              <select value={statusFiltro} onChange={(e) => setStatusFiltro(e.target.value)} className="input-field input-field--icon-left appearance-none">
                <option value="">Todos os status</option>
                <option value="Ativo">Ativo</option>
                <option value="EmFormacao">Em formação</option>
                <option value="Inativo">Inativo</option>
              </select>
            </div>
          </div>
          {filtrados.length === 0 ? (
            <EmptyState
              icon={Users}
              title={coroinhas.length === 0 ? "Nenhum coroinha cadastrado" : "Nenhum resultado"}
              description="Faça uma inscrição online ou aprove um cadastro pendente."
            />
          ) : (
            <table className="table-liturgical">
              <thead>
                <tr>
                  <th>Foto</th>
                  <th>Nome</th>
                  <th>Idade</th>
                  <th>Turma</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {filtrados.map((c) => (
                  <tr key={c.id}>
                    <td>
                      {podeEnviarFoto ? (
                        <label
                          className={`cursor-pointer inline-flex items-center gap-2 ${enviandoFotoId === c.id ? "opacity-60 pointer-events-none" : ""}`}
                          title="Enviar foto"
                        >
                          <CoroinhaAvatar nome={c.nome} fotoUrl={mediaUrl(c.foto_url)} size="sm" />
                          <Upload className="size-4 text-muted-foreground" aria-hidden />
                          <input
                            type="file"
                            accept="image/*"
                            className="sr-only"
                            disabled={enviandoFotoId === c.id}
                            onChange={(e) => {
                              const f = e.target.files?.[0];
                              if (f) enviarFoto(c.id, f);
                              e.target.value = "";
                            }}
                          />
                        </label>
                      ) : (
                        <CoroinhaAvatar nome={c.nome} fotoUrl={mediaUrl(c.foto_url)} size="sm" />
                      )}
                    </td>
                    <td className="font-medium">{c.nome}</td>
                    <td>{c.idade}</td>
                    <td>{turmaLabel(c.turma)}</td>
                    <td><StatusBadge status={c.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </StaffPage>
    </StaffLayout>
  );
}
