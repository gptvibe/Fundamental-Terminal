FROM node:20-alpine AS deps

WORKDIR /app
COPY package*.json ./
RUN npm ci

FROM node:20-alpine AS builder

WORKDIR /app
ARG BACKEND_API_BASE_URL=http://backend:8000
ARG NEXT_PUBLIC_DEMO_MODE=false
ARG NEXT_PUBLIC_PERFORMANCE_AUDIT_ENABLED=false
ENV NEXT_TELEMETRY_DISABLED=1
ENV BACKEND_API_BASE_URL=${BACKEND_API_BASE_URL}
ENV NEXT_PUBLIC_DEMO_MODE=${NEXT_PUBLIC_DEMO_MODE}
ENV NEXT_PUBLIC_PERFORMANCE_AUDIT_ENABLED=${NEXT_PUBLIC_PERFORMANCE_AUDIT_ENABLED}

COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS runner

WORKDIR /app
ARG BACKEND_API_BASE_URL=http://backend:8000
ARG NEXT_PUBLIC_DEMO_MODE=false
ARG NEXT_PUBLIC_PERFORMANCE_AUDIT_ENABLED=false
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    BACKEND_API_BASE_URL=${BACKEND_API_BASE_URL} \
    NEXT_PUBLIC_DEMO_MODE=${NEXT_PUBLIC_DEMO_MODE} \
    NEXT_PUBLIC_PERFORMANCE_AUDIT_ENABLED=${NEXT_PUBLIC_PERFORMANCE_AUDIT_ENABLED} \
    HOSTNAME=0.0.0.0 \
    PORT=3000

RUN addgroup -S nextjs -g 1001 \
    && adduser -S nextjs -u 1001 -G nextjs \
    && mkdir -p /app/.next/cache \
    && chown -R nextjs:nextjs /app/.next

COPY --from=builder --chown=nextjs:nextjs /app/public ./public
COPY --from=builder --chown=nextjs:nextjs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nextjs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
