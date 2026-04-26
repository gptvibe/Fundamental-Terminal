import { describe, expect, it } from "vitest";

describe("next security headers", () => {
  it("keeps production hardening headers enabled for all routes", async () => {
    const configModule = await import("./next.config.mjs");
    const headers = await configModule.default.headers();

    expect(headers).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          source: "/:path*",
          headers: expect.arrayContaining([
            expect.objectContaining({ key: "X-Content-Type-Options", value: "nosniff" }),
            expect.objectContaining({ key: "X-Frame-Options", value: "DENY" }),
            expect.objectContaining({ key: "Referrer-Policy", value: "strict-origin-when-cross-origin" }),
            expect.objectContaining({ key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" }),
          ]),
        }),
      ]),
    );
  });
});
