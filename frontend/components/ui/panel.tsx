import type { ReactNode } from "react";
import { clsx } from "clsx";

interface PanelProps {
  title: ReactNode;
  subtitle?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  bodyId?: string;
  bodyHidden?: boolean;
  variant?: "default" | "subtle" | "hero" | "ghost";
}

export function Panel({
  title,
  subtitle,
  aside,
  children,
  className,
  bodyClassName,
  bodyId,
  bodyHidden = false,
  variant = "default",
}: PanelProps) {
  return (
    <section className={clsx("panel", `panel-${variant}`, className)}>
      <div className="panel-header">
        <div>
          <h2 className="panel-title">{title}</h2>
          {subtitle ? <p className="panel-subtitle">{subtitle}</p> : null}
        </div>
        {aside}
      </div>
      <div id={bodyId} className={clsx("panel-body", bodyClassName)} hidden={bodyHidden}>
        {children}
      </div>
    </section>
  );
}
