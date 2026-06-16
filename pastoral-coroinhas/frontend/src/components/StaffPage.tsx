import type { ReactNode } from "react";
import { PageHeader } from "@/components/PageHeader";

interface StaffPageProps {
  title: string;
  description?: string;
  onLogout: () => void;
  actions?: ReactNode;
  children: ReactNode;
}

export function StaffPage({ title, description, onLogout, actions, children }: StaffPageProps) {
  return (
    <>
      <PageHeader title={title} description={description} onLogout={onLogout} actions={actions} />
      {children}
    </>
  );
}
