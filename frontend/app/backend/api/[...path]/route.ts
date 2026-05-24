import * as proxyTransport from "./proxy";

const REQUEST_HOP_BY_HOP_HEADERS = new Set([
  "accept-encoding",
  "connection",
  "content-length",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

type RouteContext = {
  params: {
    path: string[];
  };
};

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function resolveBackendApiBaseUrl(): string {
  return (process.env.BACKEND_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
}

function buildBackendRequestHeaders(request: Request): Headers {
  const headers = new Headers();

  request.headers.forEach((value, key) => {
    if (REQUEST_HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
      return;
    }
    headers.append(key, value);
  });

  const requestUrl = new URL(request.url);
  headers.set("x-forwarded-host", requestUrl.host);
  headers.set("x-forwarded-proto", requestUrl.protocol.replace(/:$/, ""));

  return headers;
}

async function proxyBackendRequest(request: Request, { params }: RouteContext): Promise<Response> {
  const requestUrl = new URL(request.url);
  const path = params.path.map((segment) => encodeURIComponent(segment)).join("/");
  const backendUrl = `${resolveBackendApiBaseUrl()}/api/${path}${requestUrl.search}`;

  const init: {
    method: string;
    headers: Headers;
    body?: ArrayBuffer;
  } = {
    method: request.method,
    headers: buildBackendRequestHeaders(request),
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }

  try {
    return await proxyTransport.executeBackendRequest(backendUrl, init);
  } catch {
    return Response.json({ detail: "Backend proxy request failed" }, { status: 502 });
  }
}

export const GET = proxyBackendRequest;
export const HEAD = proxyBackendRequest;
export const POST = proxyBackendRequest;
export const PUT = proxyBackendRequest;
export const PATCH = proxyBackendRequest;
export const DELETE = proxyBackendRequest;
export const OPTIONS = proxyBackendRequest;