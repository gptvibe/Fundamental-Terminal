import type { ReactNode } from "react";

import { CompanyLayoutProvider } from "@/components/layout/company-layout-context";
import { CompanySubnav } from "@/components/layout/company-subnav";

export default function CompanyTickerLayout({
  children,
  params
}: Readonly<{
  children: ReactNode;
  params: { ticker: string };
}>) {
  const ticker = decodeURIComponent(params.ticker).toUpperCase();

  return (
    <CompanyLayoutProvider>
      <div className="company-workspace-stack">
        <CompanySubnav ticker={ticker} />
        {children}
      </div>
    </CompanyLayoutProvider>
  );
}
