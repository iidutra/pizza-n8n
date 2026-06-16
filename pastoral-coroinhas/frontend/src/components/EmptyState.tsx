import type { LucideIcon } from "lucide-react";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
}

export function EmptyState({ icon: Icon, title, description }: EmptyStateProps) {
  return (
    <div className="py-12 px-6 text-center">
      <div className="size-14 rounded-full bg-muted mx-auto grid place-items-center mb-4">
        <Icon className="size-7 text-muted-foreground" aria-hidden />
      </div>
      <p className="font-medium text-foreground">{title}</p>
      <p className="text-sm text-muted-foreground mt-1 max-w-sm mx-auto">{description}</p>
    </div>
  );
}
