import type { ReactNode } from "react";
import { clsx } from "clsx";

interface PanelProps {
  title: string;
  subtitle?: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Panel({ title, subtitle, aside, children, className }: PanelProps) {
  return (
    <section className={clsx("panel", className)}>
      <div className="panel-header">
        <div>
          <h2 className="panel-title">{title}</h2>
          {subtitle ? <div className="text-muted" style={{ marginTop: 6, fontSize: 13 }}>{subtitle}</div> : null}
        </div>
        {aside}
      </div>
      <div className="panel-body">{children}</div>
    </section>
  );
}
