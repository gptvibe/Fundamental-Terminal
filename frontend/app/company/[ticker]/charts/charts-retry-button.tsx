"use client";

import { useRouter } from "next/navigation";

export function ChartsRetryButton() {
  const router = useRouter();

  return (
    <button
      type="button"
      className="ticker-button workspace-state-button"
      onClick={() => {
        router.refresh();
      }}
    >
      Try again
    </button>
  );
}
