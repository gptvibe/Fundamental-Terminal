import type { ReactNode } from "react";
import { clsx } from "clsx";

interface PanelProps {
  title: ReactNode;
  subtitle?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  variant?: "default" | "subtle" | "hero" | "ghost";
}

export function Panel({ title, subtitle, aside, children, className, variant = "default" }: PanelProps) {
  return (
    <section className={clsx("panel", `panel-${variant}`, className)}>
      <div className="panel-header">
        <div>
          <h2 className="panel-title">{title}</h2>
          {subtitle ? <p className="panel-subtitle">{subtitle}</p> : null}
        </div>
        {aside}
      </div>
      <div className="panel-body">{children}</div>
    </section>
  );
}
