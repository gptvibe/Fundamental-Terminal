import { RefreshState } from "@/lib/types";

export function StatusPill({ state }: { state: RefreshState }) {
  const toneClass =
    state.reason === "fresh"
      ? "tone-fresh"
      : state.reason === "missing"
        ? "tone-pending"
        : state.reason === "stale"
          ? "tone-stale"
          : "tone-idle";
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
    <span className={`pill status-pill ${toneClass}`}>
      {stateLabel} · {reasonLabel}
    </span>
  );
}
