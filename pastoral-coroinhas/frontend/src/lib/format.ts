export function formatarCpf(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 11);
  if (digits.length <= 3) return digits;
  if (digits.length <= 6) return `${digits.slice(0, 3)}.${digits.slice(3)}`;
  if (digits.length <= 9) return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6)}`;
  return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6, 9)}-${digits.slice(9)}`;
}

/** Detecta digitação de e-mail antes do @ (evita máscara de CPF comer as letras). */
export function pareceEmail(value: string): boolean {
  return /[a-zA-Z@]/.test(value);
}

export function turmaLabel(turma: string): string {
  const map: Record<string, string> = {
    Iniciante: "Iniciante",
    Intermediario: "Intermediário",
    Avancado: "Avançado",
  };
  return map[turma] || turma;
}

export function categoriaDocumentoLabel(categoria: string): string {
  const map: Record<string, string> = {
    Liturgia: "Liturgia",
    Formacao: "Formação",
    Ritual: "Ritual",
    Outro: "Outro",
  };
  return map[categoria] || categoria;
}
