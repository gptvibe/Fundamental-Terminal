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
    <div className="panel workspace-error-state">
      <h2 className="workspace-state-title">Company workspace failed to load</h2>
      <p className="text-muted workspace-state-copy">
        Cached SEC-first data is still available after a retry. If this persists, queue a refresh from the company console.
      </p>
      <button type="button" className="ticker-button workspace-state-button" onClick={reset}>
        Retry route
      </button>
    </div>
  );
}
