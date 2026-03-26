import type { ConsoleEntry } from "@/lib/types";

interface StatusConsoleProps {
  entries: ConsoleEntry[];
  connectionState: "idle" | "connecting" | "open" | "closed" | "error";
}

export function StatusConsole({ entries, connectionState }: StatusConsoleProps) {
  return (
    <div className="status-console">
      <div className="status-console-header">
        <span>Live Updates</span>
        <span>{labelForConnectionState(connectionState)}</span>
      </div>
      {entries.length ? (
        entries.map((entry) => (
          <div key={entry.id} className="status-console-entry">
            <span className="status-console-time">{formatTime(entry.timestamp)}</span>
            <span className={`status-console-stage ${classNameForLevel(entry.level)}`}>{entry.stage}</span>
            {(entry.ticker || entry.kind || entry.trace_id) ? (
              <span className="text-muted" style={{ fontSize: 11 }}>
                {[entry.ticker, entry.kind, entry.trace_id ? `#${entry.trace_id.slice(0, 8)}` : null].filter(Boolean).join(" · ")}
              </span>
            ) : null}
            <span className={`status-console-message ${entry.level === "error" ? "status-console-message-error" : ""}`}>
              {entry.message}
            </span>
          </div>
        ))
      ) : (
        <div className="status-console-empty">No updates yet. Start a refresh to follow progress here.</div>
      )}
    </div>
  );
}

function formatTime(timestamp: string): string {
  return new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  }).format(new Date(timestamp));
}

function classNameForLevel(level: ConsoleEntry["level"]): string {
  if (level === "success") {
    return "status-console-level-success";
  }
  if (level === "error") {
    return "status-console-level-error";
  }
  return "status-console-level-info";
}

function labelForConnectionState(connectionState: StatusConsoleProps["connectionState"]): string {
  switch (connectionState) {
    case "connecting":
      return "Connecting";
    case "open":
      return "Live";
    case "closed":
      return "Paused";
    case "error":
      return "Connection issue";
    default:
      return "Ready";
  }
}
