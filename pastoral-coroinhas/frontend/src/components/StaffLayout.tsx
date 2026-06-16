"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Sidebar, dashboardNav } from "@/components/Sidebar";
import { LoadingScreen } from "@/components/LoadingScreen";
import { clearTokens, getUsuario } from "@/lib/api";
import type { Usuario } from "@/types";

const STAFF = ["Coordenador", "Secretario", "Padre"];
const GESTORES = ["Coordenador", "Secretario"];

export function podeGerenciarCoroinhas(tipoPerfil: string): boolean {
  return GESTORES.includes(tipoPerfil);
}

export function ReadOnlyGestorBanner({ tipoPerfil }: { tipoPerfil?: string }) {
  if (!tipoPerfil || podeGerenciarCoroinhas(tipoPerfil)) return null;
  return (
    <p className="mb-4 text-sm text-muted-foreground bg-muted/50 border border-border rounded-lg px-4 py-3">
      Seu perfil tem acesso somente leitura. Coordenador ou secretário podem alterar dados nesta área.
    </p>
  );
}

export function useStaffAuth() {
  const router = useRouter();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const u = getUsuario<Usuario>();
    if (!u) {
      router.push("/login");
      return;
    }
    if (!STAFF.includes(u.tipo_perfil)) {
      router.push("/portal");
      return;
    }
    setUsuario(u);
    setReady(true);
  }, [router]);

  function sair() {
    clearTokens();
    router.push("/login");
  }

  return { usuario, ready, sair };
}

export function StaffLayout({
  children,
  loading,
}: {
  children: React.ReactNode;
  loading?: boolean;
}) {
  const { usuario, ready, sair } = useStaffAuth();

  if (!ready) return <LoadingScreen />;

  return (
    <div className="flex min-h-screen text-foreground">
      <Sidebar groups={dashboardNav} subtitle={usuario?.nome} />
      <main className="flex-1 p-6 md:p-8 overflow-auto">
        {loading ? <LoadingScreen /> : children}
      </main>
    </div>
  );
}

export { STAFF, GESTORES };
