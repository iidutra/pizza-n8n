"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { ArrowLeft, Calendar, KeyRound, Loader2, User } from "lucide-react";
import { InputField } from "@/components/FormField";
import { apiFetch, normalizarCpf } from "@/lib/api";
import { formatarCpf } from "@/lib/format";

export default function RecuperarSenhaPage() {
  const router = useRouter();
  const [cpf, setCpf] = useState("");
  const [dataNascimento, setDataNascimento] = useState("");
  const [novaSenha, setNovaSenha] = useState("");
  const [confirmarSenha, setConfirmarSenha] = useState("");
  const [erro, setErro] = useState("");
  const [sucesso, setSucesso] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setErro("");
    setLoading(true);
    try {
      await apiFetch("/auth/recuperar-senha", {
        method: "POST",
        auth: false,
        body: JSON.stringify({
          cpf: normalizarCpf(cpf),
          data_nascimento: dataNascimento,
          nova_senha: novaSenha,
          confirmar_senha: confirmarSenha,
        }),
      });
      setSucesso(true);
      setTimeout(() => router.push("/login"), 2000);
    } catch (err) {
      setErro(err instanceof Error ? err.message : "CPF ou data de nascimento incorretos.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md card-liturgical shadow-elegant p-8">
        <div className="flex items-center gap-3 mb-6">
          <div className="size-11 rounded-full bg-muted grid place-items-center">
            <KeyRound className="size-5 text-burgundy" aria-hidden />
          </div>
          <div>
            <h1 className="font-display text-2xl font-semibold text-burgundy">Recuperar senha</h1>
            <p className="text-sm text-muted-foreground">CPF + data de nascimento do coroinha</p>
          </div>
        </div>

        {sucesso ? (
          <p className="text-emerald-700 font-medium text-center py-4">Senha alterada! Redirecionando...</p>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <InputField
              label="CPF"
              icon={User}
              value={cpf}
              onChange={(e) => setCpf(formatarCpf(e.target.value))}
              required
            />
            <InputField
              label="Data de nascimento do coroinha"
              icon={Calendar}
              type="date"
              value={dataNascimento}
              onChange={(e) => setDataNascimento(e.target.value)}
              required
            />
            <InputField
              label="Nova senha"
              icon={KeyRound}
              type="password"
              value={novaSenha}
              onChange={(e) => setNovaSenha(e.target.value)}
              minLength={6}
              required
            />
            <InputField
              label="Confirmar senha"
              icon={KeyRound}
              type="password"
              value={confirmarSenha}
              onChange={(e) => setConfirmarSenha(e.target.value)}
              minLength={6}
              required
            />
            {erro && (
              <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-lg" role="alert">
                {erro}
              </p>
            )}
            <button type="submit" disabled={loading} className="btn-primary w-full">
              {loading ? (
                <>
                  <Loader2 className="size-4 animate-spin" aria-hidden />
                  Salvando...
                </>
              ) : (
                "Alterar senha"
              )}
            </button>
          </form>
        )}

        <p className="mt-4 text-center text-sm">
          <Link href="/login" className="inline-flex items-center gap-1 text-burgundy hover:underline">
            <ArrowLeft className="size-3.5" aria-hidden />
            Voltar ao login
          </Link>
        </p>
      </div>
    </main>
  );
}
