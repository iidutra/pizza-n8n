export function StatusBadge({ status }: { status: string }) {
  const label =
    status === "EmFormacao" ? "Em formação" : status === "Ativo" ? "Ativo" : status;

  const cls =
    status === "Ativo"
      ? "badge-ativo"
      : status === "EmFormacao"
        ? "badge-formacao"
        : "badge-formacao";

  return <span className={cls}>{label}</span>;
}
