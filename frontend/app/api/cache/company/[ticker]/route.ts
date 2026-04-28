import { revalidateTag } from "next/cache";
import { NextResponse } from "next/server";

import { buildCompanyFinancialsCacheTags, normalizeCompanyWorkspaceCacheTicker } from "@/lib/company-workspace-cache-tags";

type RouteContext = {
  params: {
    ticker: string;
  };
};

export async function POST(_request: Request, { params }: RouteContext) {
  const ticker = normalizeCompanyWorkspaceCacheTicker(params.ticker);
  const tags = buildCompanyFinancialsCacheTags(ticker);

  for (const tag of tags) {
    revalidateTag(tag);
  }

  return NextResponse.json({ ok: true, ticker, tags });
}
