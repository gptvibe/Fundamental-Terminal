import { RefreshState } from "@/lib/types";

export function StatusPill({ state }: { state: RefreshState }) {
  const color =
    state.reason === "fresh"
      ? "#00FF41"
      : state.reason === "stale"
        ? "#FFD700"
        : state.reason === "missing"
          ? "#00E5FF"
          : "#8b949e";
  const stateLabel = state.triggered ? "Updating" : "Ready";
  const reasonLabel =
    state.reason === "fresh"
      ? "Up to date"
      : state.reason === "stale"
        ? "Needs refresh"
        : state.reason === "missing"
          ? "Getting data"
          : state.reason === "manual"
            ? "Requested"
            : "Ready";

  return (
    <span className="pill" style={{ borderColor: `${color}66`, color }}>
      {stateLabel} · {reasonLabel}
    </span>
  );
}
