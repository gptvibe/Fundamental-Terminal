import { redirect } from "next/navigation";

export default function CompanyStakesRedirectPage({
  params
}: Readonly<{
  params: { ticker: string };
}>) {
  redirect(`/company/${encodeURIComponent(params.ticker)}/ownership-changes`);
}
