import type { ReactNode } from "react";

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
    <div className="company-workspace-stack">
      <CompanySubnav ticker={ticker} />
      {children}
    </div>
  );
}
