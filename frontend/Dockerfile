# syntax=docker/dockerfile:1.7
FROM node:20-bookworm-slim AS deps
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1 NODE_ENV=development
COPY package.json package-lock.json ./
RUN npm ci --include=dev --no-audit --no-fund \
    && test -x node_modules/.bin/tsc \
    && test -x node_modules/.bin/next

FROM node:20-bookworm-slim AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1 NODE_ENV=production
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ARG NEXT_PUBLIC_OPENEDX_CMS_BASE_URL=http://studio.local.openedx.io
ARG NEXT_PUBLIC_AUTO_CMS_SESSION_LOGIN=true
ARG NEXT_PUBLIC_APP_ENV=production
ARG NEXT_PUBLIC_ENABLE_DIAGNOSTICS_UI=false
ARG NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.64.16.5.7.1
ARG NEXT_PUBLIC_API_GET_TIMEOUT_MS=45000
ARG NEXT_PUBLIC_API_WRITE_TIMEOUT_MS=120000
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL} \
    NEXT_PUBLIC_OPENEDX_CMS_BASE_URL=${NEXT_PUBLIC_OPENEDX_CMS_BASE_URL} \
    NEXT_PUBLIC_AUTO_CMS_SESSION_LOGIN=${NEXT_PUBLIC_AUTO_CMS_SESSION_LOGIN} \
    NEXT_PUBLIC_APP_ENV=${NEXT_PUBLIC_APP_ENV} \
    NEXT_PUBLIC_ENABLE_DIAGNOSTICS_UI=${NEXT_PUBLIC_ENABLE_DIAGNOSTICS_UI} \
    NEXT_PUBLIC_APP_VERSION=${NEXT_PUBLIC_APP_VERSION} \
    NEXT_PUBLIC_API_GET_TIMEOUT_MS=${NEXT_PUBLIC_API_GET_TIMEOUT_MS} \
    NEXT_PUBLIC_API_WRITE_TIMEOUT_MS=${NEXT_PUBLIC_API_WRITE_TIMEOUT_MS}
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run lint \
    && npm run typecheck \
    && npm run build

FROM node:20-bookworm-slim AS runner
ARG APP_UID=10001
ARG APP_GID=10001
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production \
    HOME=/tmp \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN groupadd --gid "${APP_GID}" aiweb \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --no-create-home --shell /usr/sbin/nologin aiweb
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
RUN chmod -R a-w /app
USER ${APP_UID}:${APP_GID}
EXPOSE 3000
CMD ["node", "server.js"]
