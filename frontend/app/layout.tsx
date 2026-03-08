import type { ReactNode } from "react";
import type { Metadata } from "next";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";
import "./globals.css";

import { AppChrome } from "@/components/layout/app-chrome";

export const metadata: Metadata = {
  title: "Fundamental Terminal",
  description: "Bloomberg-style fundamentals terminal built with Next.js"
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <AppChrome>{children}</AppChrome>
      </body>
    </html>
  );
}
