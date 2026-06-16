"use client";

import { useEffect, useState } from "react";
import { Check, X } from "lucide-react";
import { StaffLayout, useStaffAuth, podeGerenciarCoroinhas, ReadOnlyGestorBanner } from "@/components/StaffLayout";
import { StaffPage } from "@/components/StaffPage";
import { EmptyState } from "@/components/EmptyState";
import { ClipboardList } from "lucide-react";
import { apiFetch } from "@/lib/api";
import type { Inscricao } from "@/types";

export default function InscricoesPage() {
  const { ready, sair, usuario } = useStaffAuth();
  const podeEditar = usuario ? podeGerenciarCoroinhas(usuario.tipo_perfil) : false;
  const [inscricoes, setInscricoes] = useState<Inscricao[]>([]);
  const [loading, setLoading] = useState(true);

  function load() {
    apiFetch<{ results?: Inscricao[] } | Inscricao[]>("/inscricoes/?status=Pendente")
      .then((d) => setInscricoes(Array.isArray(d) ? d : (d.results ?? [])))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (ready) load();
  }, [ready]);

  async function aprovar(id: number) {
    await apiFetch(`/inscricoes/${id}/aprovar/`, { method: "POST" });
    load();
  }

  async function rejeitar(id: number) {
    await apiFetch(`/inscricoes/${id}/rejeitar/`, { method: "POST" });
    load();
  }

  return (
    <StaffLayout loading={loading}>
      <StaffPage title="Inscrições pendentes" description="Aprove ou rejeite fichas enviadas online." onLogout={sair}>
        <ReadOnlyGestorBanner tipoPerfil={usuario?.tipo_perfil} />
        {inscricoes.length === 0 ? (
          <EmptyState icon={ClipboardList} title="Nenhuma inscrição pendente" description="Novas inscrições aparecerão aqui." />
        ) : (
          <div className="space-y-4">
            {inscricoes.map((i) => (
              <div key={i.id} className="card-liturgical p-5 flex flex-col sm:flex-row sm:items-center gap-4">
                <div className="flex-1">
                  <p className="font-semibold">{i.dados.coroinha?.nome ?? "Sem nome"}</p>
                  <p className="text-sm text-muted-foreground">
                    Nasc.: {i.dados.coroinha?.data_nascimento} · CPF resp.: {i.dados.responsavel?.cpf}
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Enviada em {new Date(i.criado_em).toLocaleDateString("pt-BR")}
                  </p>
                </div>
                {podeEditar && (
                <div className="flex gap-2">
                  <button type="button" onClick={() => aprovar(i.id)} className="btn-primary text-sm">
                    <Check className="size-4" aria-hidden /> Aprovar
                  </button>
                  <button type="button" onClick={() => rejeitar(i.id)} className="btn-outline text-sm text-destructive">
                    <X className="size-4" aria-hidden /> Rejeitar
                  </button>
                </div>
                )}
              </div>
            ))}
          </div>
        )}
      </StaffPage>
    </StaffLayout>
  );
}
