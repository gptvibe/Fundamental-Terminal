import { request as httpRequest, type IncomingHttpHeaders } from "node:http";
import { request as httpsRequest } from "node:https";

const RESPONSE_TRANSPORT_HEADERS = new Set([
  "connection",
  "content-encoding",
  "content-length",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

function normalizeProxyResponseHeaderValue(key: string, value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  if (key.toLowerCase() === "last-modified") {
    const pythonBytesMatch = /^b(['"])(.*)\1$/.exec(trimmed);
    if (pythonBytesMatch) {
      return pythonBytesMatch[2];
    }
  }

  return trimmed;
}

function appendProxyResponseHeader(headers: Headers, key: string, value: string): void {
  if (RESPONSE_TRANSPORT_HEADERS.has(key.toLowerCase())) {
    return;
  }

  const normalizedValue = normalizeProxyResponseHeaderValue(key, value);
  if (!normalizedValue) {
    return;
  }

  headers.append(key, normalizedValue);
}

export function buildProxyResponseHeaders(upstreamHeaders: Headers | IncomingHttpHeaders): Headers {
  const headers = new Headers();

  if (upstreamHeaders instanceof Headers) {
    upstreamHeaders.forEach((value, key) => {
      appendProxyResponseHeader(headers, key, value);
    });
    return headers;
  }

  for (const [key, rawValue] of Object.entries(upstreamHeaders)) {
    if (rawValue === undefined) {
      continue;
    }

    if (Array.isArray(rawValue)) {
      for (const value of rawValue) {
        appendProxyResponseHeader(headers, key, value);
      }
      continue;
    }

    appendProxyResponseHeader(headers, key, rawValue);
  }

  return headers;
}

export async function executeBackendRequest(
  backendUrl: string,
  init: {
    method: string;
    headers: Headers;
    body?: ArrayBuffer;
  }
): Promise<Response> {
  const url = new URL(backendUrl);
  const requestFn = url.protocol === "https:" ? httpsRequest : httpRequest;

  return await new Promise<Response>((resolve, reject) => {
    const upstreamRequest = requestFn(
      url,
      {
        method: init.method,
        headers: Object.fromEntries(init.headers.entries()),
      },
      (upstreamResponse) => {
        const chunks: Buffer[] = [];

        upstreamResponse.on("data", (chunk) => {
          chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
        });
        upstreamResponse.on("end", () => {
          resolve(
            new Response(Buffer.concat(chunks), {
              status: upstreamResponse.statusCode ?? 502,
              statusText: upstreamResponse.statusMessage,
              headers: buildProxyResponseHeaders(upstreamResponse.headers),
            })
          );
        });
        upstreamResponse.on("error", reject);
      }
    );

    upstreamRequest.on("error", reject);

    if (init.body) {
      upstreamRequest.write(Buffer.from(init.body));
    }

    upstreamRequest.end();
  });
}