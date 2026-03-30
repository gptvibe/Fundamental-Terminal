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
      <h2 className="workspace-state-title">Research Brief failed to load</h2>
      <p className="text-muted workspace-state-copy">
        Retry the default narrative brief. If this persists, queue a background refresh from the company console and use the specialist routes while the cache refills.
      </p>
      <button type="button" className="ticker-button workspace-state-button" onClick={reset}>
        Retry brief
      </button>
    </div>
  );
}
