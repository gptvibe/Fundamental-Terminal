"use client";

import type { KeyboardEvent, ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { clsx } from "clsx";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
  "[contenteditable='true']",
].join(",");

interface DialogProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  labelledBy?: string;
  describedBy?: string;
  overlayClassName?: string;
  contentClassName?: string;
  closeOnOverlayClick?: boolean;
}

export function Dialog({
  open,
  onClose,
  children,
  labelledBy,
  describedBy,
  overlayClassName,
  contentClassName,
  closeOnOverlayClick = true,
}: DialogProps) {
  const contentRef = useRef<HTMLDivElement>(null);
  const previousActiveElementRef = useRef<HTMLElement | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted || !open) {
      return;
    }

    previousActiveElementRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const frame = window.requestAnimationFrame(() => {
      const content = contentRef.current;
      if (!content) {
        return;
      }

      const focusableElements = getFocusableElements(content);
      const target = focusableElements[0] ?? content;
      target.focus({ preventScroll: true });
    });

    return () => {
      window.cancelAnimationFrame(frame);
      document.body.style.overflow = previousOverflow;

      if (previousActiveElementRef.current?.isConnected) {
        previousActiveElementRef.current.focus({ preventScroll: true });
      }
    };
  }, [mounted, open]);

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }

    if (event.key !== "Tab") {
      return;
    }

    const content = contentRef.current;
    if (!content) {
      return;
    }

    const focusableElements = getFocusableElements(content);
    if (!focusableElements.length) {
      event.preventDefault();
      content.focus({ preventScroll: true });
      return;
    }

    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];
    const activeElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;

    if (event.shiftKey) {
      if (activeElement === firstElement || activeElement === content) {
        event.preventDefault();
        lastElement.focus({ preventScroll: true });
      }
      return;
    }

    if (activeElement === lastElement) {
      event.preventDefault();
      firstElement.focus({ preventScroll: true });
    }
  }

  if (!mounted || !open) {
    return null;
  }

  return createPortal(
    <div
      className={clsx("app-dialog-backdrop", overlayClassName)}
      onMouseDown={(event) => {
        if (closeOnOverlayClick && event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={contentRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-describedby={describedBy}
        tabIndex={-1}
        className={clsx("app-dialog-panel", contentClassName)}
        onKeyDown={handleKeyDown}
      >
        {children}
      </div>
    </div>,
    document.body
  );
}

function getFocusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter((element) => isFocusable(element));
}

function isFocusable(element: HTMLElement): boolean {
  if (element.hasAttribute("disabled") || element.getAttribute("aria-hidden") === "true") {
    return false;
  }

  if (element instanceof HTMLInputElement && element.type === "hidden") {
    return false;
  }

  const styles = window.getComputedStyle(element);
  return styles.display !== "none" && styles.visibility !== "hidden";
}