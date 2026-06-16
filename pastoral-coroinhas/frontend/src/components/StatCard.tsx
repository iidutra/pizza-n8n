import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  label: string;
  value: number | string;
  icon: LucideIcon;
  accent?: "burgundy" | "gold" | "green" | "amber" | "red";
}

const accentStyles = {
  burgundy: "bg-burgundy/10 text-burgundy",
  gold: "bg-gold/15 text-burgundy",
  green: "bg-emerald-100 text-emerald-800",
  amber: "bg-amber-100 text-amber-800",
  red: "bg-red-100 text-red-800",
};

export function StatCard({ label, value, icon: Icon, accent = "burgundy" }: StatCardProps) {
  return (
    <div className="card-liturgical p-5 flex items-start gap-4 hover:shadow-elegant transition-shadow">
      <div className={`size-10 rounded-lg grid place-items-center shrink-0 ${accentStyles[accent]}`}>
        <Icon className="size-5" aria-hidden />
      </div>
      <div>
        <p className="stat-value">{value}</p>
        <p className="text-sm text-muted-foreground mt-1">{label}</p>
      </div>
    </div>
  );
}
