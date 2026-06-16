import type { ReactNode } from "react";
import { LogOut } from "lucide-react";

interface PageHeaderProps {
  title: string;
  description?: string;
  onLogout?: () => void;
  actions?: ReactNode;
}

export function PageHeader({ title, description, onLogout, actions }: PageHeaderProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-4 mb-8">
      <div>
        <h1 className="font-display text-3xl font-semibold text-burgundy">{title}</h1>
        {description && <p className="text-muted-foreground mt-1">{description}</p>}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {actions}
        {onLogout && (
          <button
            type="button"
            onClick={onLogout}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-border bg-card hover:bg-secondary text-muted-foreground hover:text-foreground transition-colors"
          >
            <LogOut className="size-4" aria-hidden />
            Sair
          </button>
        )}
      </div>
    </div>
  );
}
