import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/font/google", () => ({
  IBM_Plex_Sans: () => ({ variable: "--font-plex-sans" }),
  IBM_Plex_Mono: () => ({ variable: "--font-plex-mono" }),
}));

const ORIGINAL_NEXT_PUBLIC_SITE_URL = process.env.NEXT_PUBLIC_SITE_URL;
const ORIGINAL_SITE_URL = process.env.SITE_URL;

async function importLayoutModule() {
  vi.resetModules();
  return import("./layout");
}

afterEach(() => {
  if (ORIGINAL_NEXT_PUBLIC_SITE_URL === undefined) {
    delete process.env.NEXT_PUBLIC_SITE_URL;
  } else {
    process.env.NEXT_PUBLIC_SITE_URL = ORIGINAL_NEXT_PUBLIC_SITE_URL;
  }

  if (ORIGINAL_SITE_URL === undefined) {
    delete process.env.SITE_URL;
  } else {
    process.env.SITE_URL = ORIGINAL_SITE_URL;
  }

  vi.resetModules();
});

describe("root metadata", () => {
  it("uses NEXT_PUBLIC_SITE_URL when configured", async () => {
    process.env.NEXT_PUBLIC_SITE_URL = "https://fundamental-terminal.example";
    delete process.env.SITE_URL;

    const { metadata, resolveMetadataBase } = await importLayoutModule();

    expect(resolveMetadataBase().href).toBe("https://fundamental-terminal.example/");
    expect(metadata.metadataBase?.href).toBe("https://fundamental-terminal.example/");
  });

  it("falls back to localhost when no valid site URL is configured", async () => {
    process.env.NEXT_PUBLIC_SITE_URL = "not a url";
    delete process.env.SITE_URL;

    const { metadata, resolveMetadataBase } = await importLayoutModule();

    expect(resolveMetadataBase().href).toBe("http://localhost:3000/");
    expect(metadata.metadataBase?.href).toBe("http://localhost:3000/");
  });
});