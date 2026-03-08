FROM node:20-alpine AS deps

WORKDIR /app
COPY package*.json ./
RUN npm ci

FROM node:20-alpine AS builder

WORKDIR /app
ARG BACKEND_API_BASE_URL=http://backend:8000
ENV NEXT_TELEMETRY_DISABLED=1
ENV BACKEND_API_BASE_URL=${BACKEND_API_BASE_URL}

COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS runner

WORKDIR /app
ARG BACKEND_API_BASE_URL=http://backend:8000
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    BACKEND_API_BASE_URL=${BACKEND_API_BASE_URL} \
    PORT=3000

COPY --from=builder /app .

EXPOSE 3000

CMD ["npm", "run", "start"]
