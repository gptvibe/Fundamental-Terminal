"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

interface DeferredClientSectionProps {
  children: ReactNode;
  placeholder?: ReactNode;
  rootMargin?: string;
  forceVisible?: boolean;
}

export function DeferredClientSection({
  children,
  placeholder = <div className="text-muted">Loading section...</div>,
  rootMargin = "240px 0px",
  forceVisible = false,
}: DeferredClientSectionProps) {
  const [visible, setVisible] = useState(false);
  const markerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (forceVisible) {
      setVisible(true);
      return;
    }

    if (visible) {
      return;
    }

    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }

    const marker = markerRef.current;
    if (!marker) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { root: null, rootMargin, threshold: 0.01 }
    );

    observer.observe(marker);
    return () => observer.disconnect();
  }, [forceVisible, rootMargin, visible]);

  return (
    <div ref={markerRef} className={visible ? "deferred-client-section-visible" : "deferred-client-section-pending"}>
      {visible ? children : placeholder}
    </div>
  );
}
