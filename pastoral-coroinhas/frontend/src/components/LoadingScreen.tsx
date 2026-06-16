export function LoadingScreen({ message = "Carregando..." }: { message?: string }) {
  return (
    <div className="min-h-[40vh] flex flex-col items-center justify-center gap-3 text-muted-foreground">
      <div className="size-8 rounded-full border-2 border-gold border-t-transparent animate-spin" aria-hidden />
      <p className="text-sm">{message}</p>
    </div>
  );
}
