"use client";

import { createContext, useCallback, useContext, useMemo, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";

import type { CompanyPayload } from "@/lib/types";

interface CompanyLayoutContextValue {
  company: CompanyPayload | null;
  publisherCount: number;
  registerPublisher: () => () => void;
  setCompany: Dispatch<SetStateAction<CompanyPayload | null>>;
}

const CompanyLayoutContext = createContext<CompanyLayoutContextValue | null>(null);

export function CompanyLayoutProvider({ children }: { children: ReactNode }) {
  const [company, setCompany] = useState<CompanyPayload | null>(null);
  const [publisherCount, setPublisherCount] = useState(0);

  const registerPublisher = useCallback(() => {
    setPublisherCount((current) => current + 1);
    return () => {
      setPublisherCount((current) => Math.max(0, current - 1));
    };
  }, []);

  const value = useMemo(
    () => ({
      company,
      publisherCount,
      registerPublisher,
      setCompany,
    }),
    [company, publisherCount, registerPublisher]
  );

  return <CompanyLayoutContext.Provider value={value}>{children}</CompanyLayoutContext.Provider>;
}

export function useCompanyLayoutContext(): CompanyLayoutContextValue | null {
  return useContext(CompanyLayoutContext);
}
