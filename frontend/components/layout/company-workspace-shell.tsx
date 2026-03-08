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
    <div className={clsx("company-workspace-shell", className)}>
      <div className={clsx("company-workspace-main", mainClassName)}>{children}</div>
      <aside className={clsx("company-workspace-rail", railClassName)}>{rail}</aside>
    </div>
  );
}
