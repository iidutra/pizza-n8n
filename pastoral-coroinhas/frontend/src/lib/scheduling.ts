export const FUNCOES_ESCALA = [
  { value: "Cruz", label: "Cruz" },
  { value: "Vela1", label: "Vela 1" },
  { value: "Vela2", label: "Vela 2" },
  { value: "Turibulo", label: "Turíbulo" },
  { value: "Naveta", label: "Naveta" },
  { value: "Missal", label: "Missal" },
  { value: "EntreOsDois", label: "Entre os dois" },
  { value: "Ofertorio", label: "Ofertório" },
  { value: "Assessor", label: "Assessor" },
] as const;

export type FuncaoEscala = (typeof FUNCOES_ESCALA)[number]["value"];

export function funcaoEscalaLabel(funcao: string | null | undefined): string {
  if (!funcao) return "";
  if (funcao === "Velas") return "Vela 1";
  return FUNCOES_ESCALA.find((f) => f.value === funcao)?.label ?? funcao;
}

export function funcoesVazias(): Record<FuncaoEscala, number | ""> {
  return FUNCOES_ESCALA.reduce(
    (acc, f) => {
      acc[f.value] = "";
      return acc;
    },
    {} as Record<FuncaoEscala, number | "">,
  );
}

export function funcoesFromItens(
  itens: { coroinha_id: number; funcao?: string | null }[],
): Record<FuncaoEscala, number | ""> {
  const base = funcoesVazias();
  for (const item of itens) {
    if (item.funcao && item.funcao in base) {
      base[item.funcao as FuncaoEscala] = item.coroinha_id;
    }
  }
  return base;
}

export function funcoesParaPayload(map: Record<FuncaoEscala, number | "">): Record<string, number> {
  const out: Record<string, number> = {};
  for (const f of FUNCOES_ESCALA) {
    const id = map[f.value];
    if (id) out[f.value] = Number(id);
  }
  return out;
}
