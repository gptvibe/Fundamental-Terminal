"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

interface DeferredClientSectionProps {
  children: ReactNode;
  placeholder?: ReactNode;
  rootMargin?: string;
}

export function DeferredClientSection({
  children,
  placeholder = <div className="text-muted">Loading section...</div>,
  rootMargin = "240px 0px"
}: DeferredClientSectionProps) {
  const [visible, setVisible] = useState(false);
  const markerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
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
  }, [rootMargin, visible]);

  return <div ref={markerRef}>{visible ? children : placeholder}</div>;
}
