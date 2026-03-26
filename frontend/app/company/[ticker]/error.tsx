"use client";

import { useEffect } from "react";

export default function CompanyRouteError({
  error,
  reset,
}: Readonly<{
  error: Error & { digest?: string };
  reset: () => void;
}>) {
  useEffect(() => {
    console.error("company route render error", error);
  }, [error]);

  return (
    <div className="panel" style={{ display: "grid", gap: 12 }}>
      <h2 style={{ margin: 0 }}>Company workspace failed to load</h2>
      <p className="text-muted" style={{ margin: 0 }}>
        Cached SEC-first data is still available after a retry. If this persists, queue a refresh from the company console.
      </p>
      <button type="button" className="ticker-button" onClick={reset} style={{ width: "fit-content" }}>
        Retry route
      </button>
    </div>
  );
}
