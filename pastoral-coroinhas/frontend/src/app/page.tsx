import Link from "next/link";
import {
  Calendar,
  Church,
  ClipboardList,
  GraduationCap,
  Heart,
  LogIn,
  Users,
} from "lucide-react";

const features = [
  { icon: Users, title: "Coroinhas", desc: "Cadastro e turmas" },
  { icon: Calendar, title: "Escalas", desc: "Missas e sorteios" },
  { icon: GraduationCap, title: "Formação", desc: "Encontros litúrgicos" },
  { icon: Heart, title: "Famílias", desc: "Portal dos pais" },
];

export default function HomePage() {
  return (
    <main className="min-h-screen flex flex-col bg-gradient-hero text-primary-foreground relative overflow-hidden">
      <div className="absolute inset-0 opacity-[0.12] sidebar-glow pointer-events-none" />

      <header className="relative z-10 p-6 flex items-center gap-3">
        <div className="size-10 rounded-full bg-gradient-gold grid place-items-center text-burgundy-deep shadow-gold">
          <Church className="size-5" aria-hidden />
        </div>
        <span className="font-display text-lg font-semibold">Pastoral dos Coroinhas</span>
      </header>

      <div className="relative z-10 flex-1 flex flex-col items-center justify-center p-8">
        <div className="max-w-2xl text-center space-y-6">
          <p className="text-xs uppercase tracking-[0.2em] text-gold-soft">Sistema Paroquial</p>
          <h1 className="font-display text-4xl md:text-5xl font-semibold text-white leading-tight">
            Pastoral dos Coroinhas
          </h1>
          <p className="text-white/75 text-lg max-w-lg mx-auto">
            Gestão de coroinhas, escalas, presenças, formações e portal das famílias.
          </p>
          <div className="flex flex-wrap gap-3 justify-center pt-2">
            <Link href="/login" className="btn-primary">
              <LogIn className="size-4" aria-hidden />
              Entrar
            </Link>
            <Link
              href="/inscricao"
              className="btn-outline border-white/25 bg-white/10 text-white hover:bg-white/15"
            >
              <ClipboardList className="size-4" aria-hidden />
              Inscrição online
            </Link>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-16 max-w-3xl w-full">
          {features.map(({ icon: Icon, title, desc }) => (
            <div
              key={title}
              className="rounded-xl bg-white/5 border border-white/10 p-4 text-center backdrop-blur-sm hover:bg-white/10 transition-colors"
            >
              <Icon className="size-6 text-gold mx-auto mb-2" aria-hidden />
              <p className="font-medium text-sm text-white">{title}</p>
              <p className="text-xs text-white/50 mt-0.5">{desc}</p>
            </div>
          ))}
        </div>

        <p className="text-sm text-white/40 italic mt-12">&ldquo;Servire Deo, regnare est.&rdquo;</p>
      </div>
    </main>
  );
}
