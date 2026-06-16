"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { ArrowLeft, KeyRound, Loader2, ShieldCheck } from "lucide-react";
import { InputField } from "@/components/FormField";
import { apiFetch, getUsuario } from "@/lib/api";
import type { Usuario } from "@/types";

export default function TrocarSenhaPage() {
  const router = useRouter();
  const [senhaAtual, setSenhaAtual] = useState("");
  const [novaSenha, setNovaSenha] = useState("");
  const [confirmarSenha, setConfirmarSenha] = useState("");
  const [erro, setErro] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setErro("");
    setLoading(true);
    try {
      await apiFetch("/auth/trocar-senha", {
        method: "POST",
        body: JSON.stringify({
          senha_atual: senhaAtual,
          nova_senha: novaSenha,
          confirmar_senha: confirmarSenha,
        }),
      });
      const u = getUsuario<Usuario>();
      if (u?.tipo_perfil === "Pai" || u?.tipo_perfil === "Coroinha") {
        router.push("/portal");
      } else {
        router.push("/dashboard");
      }
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao trocar senha");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md card-liturgical shadow-elegant p-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="size-11 rounded-full bg-amber-100 grid place-items-center">
            <ShieldCheck className="size-5 text-amber-800" aria-hidden />
          </div>
          <div>
            <h1 className="font-display text-2xl font-semibold text-burgundy">Trocar senha</h1>
            <p className="text-sm text-muted-foreground">Obrigatório no primeiro acesso</p>
          </div>
        </div>

        <p className="text-xs text-muted-foreground bg-muted/60 rounded-lg px-3 py-2 mb-6">
          Por segurança, defina uma senha pessoal antes de continuar.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <InputField
            label="Senha atual"
            icon={KeyRound}
            type="password"
            value={senhaAtual}
            onChange={(e) => setSenhaAtual(e.target.value)}
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
              "Salvar nova senha"
            )}
          </button>
        </form>

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
