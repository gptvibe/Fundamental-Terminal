import { RefreshState } from "@/lib/types";

export function StatusPill({ state }: { state: RefreshState }) {
  const tone =
    state.reason === "fresh"
      ? {
          borderColor: "color-mix(in srgb, var(--cyan) 34%, var(--panel-border))",
          background: "color-mix(in srgb, var(--cyan) 10%, var(--surface-pill-bg))",
          color: "var(--cyan)"
        }
      : state.reason === "missing"
        ? {
            borderColor: "color-mix(in srgb, var(--cyan) 24%, var(--panel-border))",
            background: "color-mix(in srgb, var(--cyan) 6%, var(--surface-pill-bg))",
            color: "color-mix(in srgb, var(--cyan) 82%, var(--text))"
          }
        : state.reason === "stale"
          ? {
              borderColor: "color-mix(in srgb, var(--surface-pill-border) 92%, transparent)",
              background: "color-mix(in srgb, var(--surface-pill-bg) 88%, transparent)",
              color: "var(--text-soft)"
            }
          : {
              borderColor: "color-mix(in srgb, var(--surface-pill-border) 88%, transparent)",
              background: "color-mix(in srgb, var(--surface-pill-bg) 82%, transparent)",
              color: "var(--text-muted)"
            };
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
    <span className="pill status-pill" style={tone}>
      {stateLabel} · {reasonLabel}
    </span>
  );
}
