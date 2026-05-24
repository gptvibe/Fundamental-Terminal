"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

interface DeferredClientSectionProps {
  children?: ReactNode;
  placeholder?: ReactNode;
  rootMargin?: string;
  forceVisible?: boolean;
  fallbackDelayMs?: number | null;
}

export function DeferredClientSection({
  children,
  placeholder = <div className="text-muted">Loading section...</div>,
  rootMargin = "240px 0px",
  forceVisible = false,
  fallbackDelayMs = null,
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

    let fallbackTimer: number | null = null;
    if (fallbackDelayMs != null && fallbackDelayMs >= 0) {
      fallbackTimer = window.setTimeout(() => {
        setVisible(true);
      }, fallbackDelayMs);
    }

    const marker = markerRef.current;
    if (!marker) {
      if (fallbackTimer != null) {
        return () => window.clearTimeout(fallbackTimer);
      }
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
    return () => {
      observer.disconnect();
      if (fallbackTimer != null) {
        window.clearTimeout(fallbackTimer);
      }
    };
  }, [fallbackDelayMs, forceVisible, rootMargin, visible]);

  return (
    <div ref={markerRef} className={visible ? "deferred-client-section-visible" : "deferred-client-section-pending"}>
      {visible ? children : placeholder}
    </div>
  );
}
