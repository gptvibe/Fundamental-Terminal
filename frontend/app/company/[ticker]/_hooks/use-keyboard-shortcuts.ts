import { useCallback, useEffect } from "react";
import { showAppToast } from "@/lib/app-toast";

export interface KeyboardShortcutConfig {
  ticker: string;
  onRefresh?: () => void;
  onSearch?: () => void;
  onWatchlist?: () => void;
  onCompare?: () => void;
  onShowHelp?: () => void;
}

/**
 * Keyboard shortcuts for the company research page:
 * - `/` - Open search
 * - `r` - Refresh data
 * - `w` - Open watchlist
 * - `c` - Open compare
 * - `?` - Show help dialog (future)
 */
export function useCompanyPageKeyboardShortcuts({
  onRefresh,
  onSearch,
  onWatchlist,
  onCompare,
  onShowHelp,
}: KeyboardShortcutConfig) {
  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.defaultPrevented) {
        return;
      }

      // Don't handle shortcuts if typing in input/textarea
      const target = event.target as HTMLElement;
      const isTypingContext =
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.contentEditable === "true";

      if (isTypingContext) {
        return;
      }

      // Only handle single key presses, not with modifiers
      if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) {
        return;
      }

      switch (event.key) {
        case "/": {
          event.preventDefault();
          onSearch?.();
          break;
        }
        case "r":
        case "R": {
          event.preventDefault();
          onRefresh?.();
          showAppToast({ message: "Refresh initiated", tone: "info" });
          break;
        }
        case "w":
        case "W": {
          event.preventDefault();
          onWatchlist?.();
          showAppToast({ message: "Watchlist opened", tone: "info" });
          break;
        }
        case "c":
        case "C": {
          event.preventDefault();
          onCompare?.();
          showAppToast({ message: "Compare page opened", tone: "info" });
          break;
        }
        case "?": {
          event.preventDefault();
          onShowHelp?.();
          showAppToast({
            message: "Keyboard shortcuts help opened",
            tone: "info",
          });
          break;
        }
      }
    },
    [onRefresh, onSearch, onWatchlist, onCompare, onShowHelp]
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [handleKeyDown]);
}
