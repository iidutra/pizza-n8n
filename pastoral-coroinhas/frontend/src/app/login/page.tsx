"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import {
  ArrowLeft,
  Church,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  LogIn,
  UserRound,
} from "lucide-react";
import { InputField } from "@/components/FormField";
import { apiFetch, clearTokens, normalizarCpf, saveUsuario, setTokens } from "@/lib/api";
import { formatarCpf, pareceEmail } from "@/lib/format";
import type { AuthResponse, Usuario } from "@/types";

function destinoAposLogin(usuario: Usuario): string {
  if (usuario.must_change_password) return "/trocar-senha";
  if (usuario.tipo_perfil === "Pai" || usuario.tipo_perfil === "Coroinha") return "/portal";
  return "/dashboard";
}

export default function LoginPage() {
  const router = useRouter();
  const [identificador, setIdentificador] = useState("");
  const [senha, setSenha] = useState("");
  const [mostrarSenha, setMostrarSenha] = useState(false);
  const [erro, setErro] = useState("");
  const [loading, setLoading] = useState(false);

  function onIdentificadorChange(value: string) {
    if (pareceEmail(value)) {
      setIdentificador(value);
    } else {
      setIdentificador(formatarCpf(value));
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setErro("");
    setLoading(true);
    clearTokens();
    try {
      const id = pareceEmail(identificador)
        ? identificador.trim().toLowerCase()
        : normalizarCpf(identificador);
      const data = await apiFetch<AuthResponse>("/auth/login", {
        method: "POST",
        auth: false,
        body: JSON.stringify({ identificador: id, senha }),
      });

      setTokens(data.access, data.refresh);
      saveUsuario(data.usuario);
      router.push(destinoAposLogin(data.usuario));
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao entrar");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md card-liturgical shadow-elegant p-8">
        <div className="flex items-center gap-3 mb-6">
          <div className="size-11 rounded-full bg-gradient-gold grid place-items-center text-burgundy-deep shadow-gold">
            <Church className="size-5" aria-hidden />
          </div>
          <div>
            <h1 className="font-display text-2xl font-semibold text-burgundy">Entrar</h1>
            <p className="text-sm text-muted-foreground">CPF ou e-mail + senha</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <InputField
            label="CPF ou e-mail"
            icon={UserRound}
            type="text"
            value={identificador}
            onChange={(e) => onIdentificadorChange(e.target.value)}
            placeholder="000.000.000-00 ou email@paroquia.org"
            autoComplete="username"
            required
          />

          <div>
            <label htmlFor="senha" className="block text-sm font-medium mb-1.5">
              Senha
            </label>
            <div className="relative">
              <KeyRound className="absolute left-3 top-1/2 z-10 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" aria-hidden />
              <input
                id="senha"
                type={mostrarSenha ? "text" : "password"}
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                className="input-field input-field--icon-left input-field--icon-right"
                autoComplete="current-password"
                required
              />
              <button
                type="button"
                onClick={() => setMostrarSenha(!mostrarSenha)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                aria-label={mostrarSenha ? "Ocultar senha" : "Mostrar senha"}
              >
                {mostrarSenha ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
          </div>

          {erro && (
            <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-lg" role="alert">
              {erro}
            </p>
          )}

          <button type="submit" disabled={loading} className="btn-primary w-full gap-2">
            {loading ? (
              <>
                <Loader2 className="size-4 animate-spin" aria-hidden />
                Entrando...
              </>
            ) : (
              <>
                <LogIn className="size-4" aria-hidden />
                Entrar
              </>
            )}
          </button>
        </form>

        <p className="mt-4 text-center text-sm">
          <Link
            href="/recuperar-senha"
            className="inline-flex items-center gap-1 text-burgundy hover:underline"
          >
            <KeyRound className="size-3.5" aria-hidden />
            Esqueci minha senha
          </Link>
        </p>

        <p className="mt-4 text-center text-sm text-muted-foreground">
          <Link href="/" className="inline-flex items-center gap-1 hover:text-foreground">
            <ArrowLeft className="size-3.5" aria-hidden />
            Voltar ao início
          </Link>
        </p>
      </div>
    </main>
  );
}
