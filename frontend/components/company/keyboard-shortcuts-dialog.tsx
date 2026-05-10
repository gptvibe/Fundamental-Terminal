"use client";

import { useEffect, useRef } from "react";
import { clsx } from "clsx";

export interface KeyboardShortcut {
  key: string;
  description: string;
  category?: string;
}

export interface KeyboardShortcutsDialogProps {
  isOpen: boolean;
  onClose: () => void;
  shortcuts: KeyboardShortcut[];
}

export function KeyboardShortcutsDialog({
  isOpen,
  onClose,
  shortcuts,
}: KeyboardShortcutsDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }

    if (isOpen) {
      if (typeof dialog.showModal === "function") {
        dialog.showModal();
      }
    } else {
      if (typeof dialog.close === "function") {
        dialog.close();
      }
    }
  }, [isOpen]);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };

    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [isOpen, onClose]);

  // Group shortcuts by category
  const groupedShortcuts = shortcuts.reduce(
    (groups, shortcut) => {
      const category = shortcut.category || "Other";
      if (!groups[category]) {
        groups[category] = [];
      }
      groups[category].push(shortcut);
      return groups;
    },
    {} as Record<string, KeyboardShortcut[]>
  );

  return (
    <dialog
      ref={dialogRef}
      className={clsx("keyboard-shortcuts-dialog", isOpen && "dialog-open")}
      onClose={onClose}
    >
      <div className="dialog-content">
        <div className="dialog-header">
          <h2 className="dialog-title">Keyboard Shortcuts</h2>
          <button
            className="dialog-close"
            onClick={onClose}
            aria-label="Close keyboard shortcuts"
          >
            ✕
          </button>
        </div>

        <div className="dialog-body">
          {Object.entries(groupedShortcuts).map(([category, items]) => (
            <section key={category} className="shortcuts-section">
              <h3 className="shortcuts-category">{category}</h3>
              <ul className="shortcuts-list">
                {items.map((shortcut, index) => (
                  <li key={index} className="shortcut-item">
                    <kbd className="shortcut-key">{shortcut.key}</kbd>
                    <span className="shortcut-description">{shortcut.description}</span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>

        <div className="dialog-footer">
          <button
            className="dialog-button dialog-button-primary"
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </div>

      {isOpen && (
        <div
          className="dialog-backdrop"
          onClick={onClose}
          aria-hidden="true"
        />
      )}
    </dialog>
  );
}
