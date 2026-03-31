import type { ReactNode } from "react";
import { clsx } from "clsx";

interface CompanyWorkspaceShellProps {
  children: ReactNode;
  rail: ReactNode;
  className?: string;
  mainClassName?: string;
  railClassName?: string;
}

export function CompanyWorkspaceShell({ children, rail, className, mainClassName, railClassName }: CompanyWorkspaceShellProps) {
  return (
    <div className={clsx("company-workspace-shell", className)} data-company-workspace-shell="true">
      <section className={clsx("company-workspace-main", mainClassName)} aria-label="Company workspace content">
        {children}
      </section>
      <aside className={clsx("company-workspace-rail", railClassName)} aria-label="Company workspace utility rail">
        {rail}
      </aside>
    </div>
  );
}
