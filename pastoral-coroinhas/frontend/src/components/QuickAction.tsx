import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { ChevronRight } from "lucide-react";

interface QuickActionProps {
  href: string;
  title: string;
  description: string;
  icon: LucideIcon;
  disabled?: boolean;
}

export function QuickAction({ href, title, description, icon: Icon, disabled }: QuickActionProps) {
  const content = (
    <>
      <div className="size-11 rounded-xl bg-gradient-gold grid place-items-center shrink-0 text-burgundy-deep shadow-gold">
        <Icon className="size-5" aria-hidden />
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-medium text-foreground group-hover:text-burgundy transition-colors">{title}</p>
        <p className="text-xs text-muted-foreground mt-0.5 truncate">{description}</p>
      </div>
      {!disabled && (
        <ChevronRight className="size-4 text-muted-foreground group-hover:text-gold shrink-0" aria-hidden />
      )}
    </>
  );

  const className =
    "card-liturgical p-4 flex items-center gap-4 group transition-all " +
    (disabled ? "opacity-50 cursor-not-allowed" : "hover:shadow-elegant hover:border-gold/40");

  if (disabled || href === "#") {
    return (
      <div className={className} title="Em breve">
        {content}
      </div>
    );
  }

  return (
    <Link href={href} className={className}>
      {content}
    </Link>
  );
}
