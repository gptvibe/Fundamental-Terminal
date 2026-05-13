import { afterEach, describe, expect, it, vi } from "vitest";

import { GET, POST } from "./route";

describe("backend api proxy route", () => {
  const originalBackendApiBaseUrl = process.env.BACKEND_API_BASE_URL;

  afterEach(() => {
    if (originalBackendApiBaseUrl === undefined) {
      delete process.env.BACKEND_API_BASE_URL;
    } else {
      process.env.BACKEND_API_BASE_URL = originalBackendApiBaseUrl;
    }
    vi.unstubAllGlobals();
  });

  it("forwards backend GET requests and strips transport headers from the response", async () => {
    process.env.BACKEND_API_BASE_URL = "http://backend:8000";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response('{"ok":true}', {
        status: 200,
        headers: {
          "content-length": "11",
          "content-type": "application/json",
          "x-test": "proxy",
        },
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(new Request("http://localhost:3000/backend/api/source-registry?view=full"), {
      params: { path: ["source-registry"] },
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://backend:8000/api/source-registry?view=full",
      expect.objectContaining({
        method: "GET",
        cache: "no-store",
        redirect: "manual",
      })
    );
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("application/json");
    expect(response.headers.get("x-test")).toBe("proxy");
    expect(response.headers.get("content-length")).toBeNull();
    await expect(response.json()).resolves.toEqual({ ok: true });
  });

  it("forwards request bodies for mutating calls", async () => {
    process.env.BACKEND_API_BASE_URL = "http://backend:8000";
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await POST(
      new Request("http://localhost:3000/backend/api/research-workspace/save?workspace_key=alpha", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          host: "localhost:3000",
        },
        body: JSON.stringify({ ok: true }),
      }),
      {
        params: { path: ["research-workspace", "save"] },
      }
    );

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://backend:8000/api/research-workspace/save?workspace_key=alpha");
    expect(init.method).toBe("POST");
    expect(init.headers).toBeInstanceOf(Headers);
    expect((init.headers as Headers).get("host")).toBeNull();
    expect((init.headers as Headers).get("content-type")).toBe("application/json");
    expect(init.body).toBeInstanceOf(ArrayBuffer);
  });
});