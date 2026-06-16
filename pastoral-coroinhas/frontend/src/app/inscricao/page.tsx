"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import {
  ArrowLeft,
  CheckCircle2,
  Church,
  Camera,
  Cross,
  FileText,
  Loader2,
  Send,
  User,
  Users,
} from "lucide-react";
import { FormSection } from "@/components/FormField";
import { apiFetchForm, normalizarCpf } from "@/lib/api";
import { formatarCpf } from "@/lib/format";

export default function InscricaoPage() {
  const [loading, setLoading] = useState(false);
  const [sucesso, setSucesso] = useState(false);
  const [erro, setErro] = useState("");
  const [cpfCoroinha, setCpfCoroinha] = useState("");
  const [cpfResponsavel, setCpfResponsavel] = useState("");

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErro("");
    setLoading(true);

    const form = new FormData(e.currentTarget);
    const payload = {
      coroinha: {
        nome: form.get("nome_coroinha"),
        data_nascimento: form.get("data_nascimento"),
        cpf: normalizarCpf(String(form.get("cpf_coroinha") || "")),
        telefone: form.get("telefone_coroinha"),
        endereco: form.get("endereco"),
        escola: form.get("escola"),
        serie: form.get("serie"),
        batizado: form.get("batizado") === "on",
        primeira_eucaristia: form.get("primeira_eucaristia") === "on",
        crisma: form.get("crisma") === "on",
      },
      responsavel: {
        cpf: normalizarCpf(String(form.get("cpf_responsavel") || "")),
        nome_mae: form.get("nome_mae"),
        nome_pai: form.get("nome_pai"),
        telefone_principal: form.get("telefone_principal"),
        whatsapp: form.get("whatsapp"),
        email: form.get("email"),
      },
    };

    const body = new FormData();
    body.append("dados", JSON.stringify(payload));
    const foto = form.get("foto") as File | null;
    if (foto && foto.size > 0) {
      body.append("foto", foto);
    }

    try {
      await apiFetchForm("/inscricoes/publica", body, { auth: false });
      setSucesso(true);
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao enviar inscrição");
    } finally {
      setLoading(false);
    }
  }

  if (sucesso) {
    return (
      <main className="min-h-screen flex items-center justify-center p-4">
        <div className="max-w-md text-center card-liturgical shadow-elegant p-8">
          <CheckCircle2 className="size-14 text-emerald-600 mx-auto mb-4" aria-hidden />
          <h1 className="font-display text-2xl font-semibold text-burgundy">Inscrição enviada!</h1>
          <p className="text-muted-foreground mt-2">Aguarde a aprovação da coordenação.</p>
          <Link href="/" className="btn-outline mt-6 inline-flex gap-2">
            <ArrowLeft className="size-4" aria-hidden />
            Voltar ao início
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen py-8 px-4">
      <div className="max-w-2xl mx-auto">
        <Link
          href="/"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-burgundy mb-4"
        >
          <ArrowLeft className="size-4" aria-hidden />
          Voltar
        </Link>

        <div className="card-liturgical shadow-elegant p-6 md:p-8">
          <div className="flex items-center gap-3 mb-6">
            <div className="size-11 rounded-full bg-gradient-gold grid place-items-center text-burgundy-deep">
              <Church className="size-5" aria-hidden />
            </div>
            <div>
              <h1 className="font-display text-3xl font-semibold text-burgundy">Inscrição Online</h1>
              <p className="text-muted-foreground text-sm">Substitui a ficha de papel.</p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-8">
            <FormSection title="Dados do coroinha" icon={User}>
              <div className="grid gap-4">
                <input name="nome_coroinha" placeholder="Nome completo *" required className="input-field" />
                <input name="data_nascimento" type="date" required className="input-field" aria-label="Data de nascimento" />
                <input
                  name="cpf_coroinha"
                  placeholder="CPF (opcional)"
                  className="input-field"
                  value={cpfCoroinha}
                  onChange={(e) => setCpfCoroinha(formatarCpf(e.target.value))}
                />
                <input name="telefone_coroinha" placeholder="Telefone" className="input-field" />
                <input name="endereco" placeholder="Endereço" className="input-field" />
                <div className="grid sm:grid-cols-2 gap-4">
                  <input name="escola" placeholder="Escola" className="input-field" />
                  <input name="serie" placeholder="Série" className="input-field" />
                </div>
              </div>
            </FormSection>

            <FormSection title="Responsáveis" icon={Users}>
              <div className="grid gap-4">
                <input
                  name="cpf_responsavel"
                  placeholder="CPF do responsável *"
                  required
                  className="input-field"
                  value={cpfResponsavel}
                  onChange={(e) => setCpfResponsavel(formatarCpf(e.target.value))}
                />
                <div className="grid sm:grid-cols-2 gap-4">
                  <input name="nome_mae" placeholder="Nome da mãe" className="input-field" />
                  <input name="nome_pai" placeholder="Nome do pai" className="input-field" />
                </div>
                <div className="grid sm:grid-cols-2 gap-4">
                  <input name="telefone_principal" placeholder="Telefone principal" className="input-field" />
                  <input name="whatsapp" placeholder="WhatsApp" className="input-field" />
                </div>
                <input name="email" type="email" placeholder="E-mail" className="input-field" />
              </div>
            </FormSection>

            <FormSection title="Foto do coroinha" icon={Camera}>
              <p className="text-sm text-muted-foreground mb-2">
                Foto de rosto para identificação nas escalas (opcional, pode enviar depois).
              </p>
              <input
                name="foto"
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="input-field file:mr-3 file:rounded-md file:border-0 file:bg-secondary file:px-3 file:py-1.5 file:text-sm"
              />
            </FormSection>

            <FormSection title="Documentos" icon={FileText}>
              <p className="text-sm text-muted-foreground">
                Foto, certidão de nascimento e termo de autorização podem ser anexados após a inscrição (recurso futuro).
              </p>
            </FormSection>

            <FormSection title="Dados religiosos" icon={Cross}>
              <div className="flex flex-wrap gap-4 text-sm">
                {[
                  { name: "batizado", label: "Batizado" },
                  { name: "primeira_eucaristia", label: "Primeira Eucaristia" },
                  { name: "crisma", label: "Crisma" },
                ].map((item) => (
                  <label
                    key={item.name}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border hover:bg-secondary cursor-pointer transition-colors"
                  >
                    <input name={item.name} type="checkbox" className="accent-[var(--burgundy)] size-4" />
                    {item.label}
                  </label>
                ))}
              </div>
            </FormSection>

            {erro && (
              <p className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg" role="alert">
                {erro}
              </p>
            )}

            <div className="flex flex-wrap gap-3 pt-2">
              <Link href="/" className="btn-outline">
                Cancelar
              </Link>
              <button type="submit" disabled={loading} className="btn-primary">
                {loading ? (
                  <>
                    <Loader2 className="size-4 animate-spin" aria-hidden />
                    Enviando...
                  </>
                ) : (
                  <>
                    <Send className="size-4" aria-hidden />
                    Enviar inscrição
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </main>
  );
}
