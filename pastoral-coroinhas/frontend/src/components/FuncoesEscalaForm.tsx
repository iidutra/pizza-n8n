"use client";

import type { Coroinha } from "@/types";
import { FUNCOES_ESCALA, type FuncaoEscala } from "@/lib/scheduling";

interface FuncoesEscalaFormProps {
  coroinhas: Coroinha[];
  valores: Record<FuncaoEscala, number | "">;
  onChange: (valores: Record<FuncaoEscala, number | "">) => void;
  compact?: boolean;
}

export function FuncoesEscalaForm({ coroinhas, valores, onChange, compact }: FuncoesEscalaFormProps) {
  return (
    <div className={`space-y-2 ${compact ? "" : "p-3 rounded-lg border border-border bg-muted/30"}`}>
      {!compact && (
        <p className="text-xs text-muted-foreground">
          Funções litúrgicas (opcional) — selecione um coroinha para cada função desejada.
        </p>
      )}
      <div className="grid sm:grid-cols-2 gap-2">
        {FUNCOES_ESCALA.map((f) => (
          <label key={f.value} className="text-sm">
            <span className="text-muted-foreground text-xs block mb-1">{f.label}</span>
            <select
              value={valores[f.value] === "" ? "" : String(valores[f.value])}
              onChange={(e) =>
                onChange({
                  ...valores,
                  [f.value]: e.target.value ? Number(e.target.value) : "",
                })
              }
              className="input-field text-sm"
            >
              <option value="">—</option>
              {coroinhas.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nome}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
    </div>
  );
}
