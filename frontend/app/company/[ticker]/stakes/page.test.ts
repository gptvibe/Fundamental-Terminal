import { describe, expect, it, vi } from "vitest";

import { redirect } from "next/navigation";
import CompanyStakesRedirectPage from "@/app/company/[ticker]/stakes/page";

vi.mock("next/navigation", () => ({
  redirect: vi.fn(),
}));

describe("CompanyStakesRedirectPage", () => {
  it("redirects the legacy stakes route to ownership-changes", () => {
    CompanyStakesRedirectPage({ params: { ticker: "ACME INC" } });

    expect(redirect).toHaveBeenCalledWith("/company/ACME%20INC/ownership-changes");
  });
});
