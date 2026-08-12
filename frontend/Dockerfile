# syntax=docker/dockerfile:1.7
FROM node:20-bookworm-slim AS deps
ARG NPM_VERSION=10.9.2
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=development \
    NPM_CONFIG_FETCH_RETRIES=5 \
    NPM_CONFIG_FETCH_RETRY_FACTOR=2 \
    NPM_CONFIG_FETCH_RETRY_MINTIMEOUT=20000 \
    NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT=120000 \
    NPM_CONFIG_FETCH_TIMEOUT=300000 \
    NPM_CONFIG_MAXSOCKETS=4 \
    NPM_CONFIG_REGISTRY=https://registry.npmjs.org/
COPY package.json package-lock.json .npmrc ./
RUN --mount=type=cache,id=ai-server-frontend-npm,target=/root/.npm,sharing=locked \
    set -eux; \
    pin_attempt=1; \
    while ! npm install --global "npm@${NPM_VERSION}" --no-audit --no-fund --registry="${NPM_CONFIG_REGISTRY}"; do \
      if [ "$pin_attempt" -ge 3 ]; then \
        echo "Unable to pin npm after ${pin_attempt} attempts" >&2; \
        exit 1; \
      fi; \
      sleep $((pin_attempt * 10)); \
      pin_attempt=$((pin_attempt + 1)); \
    done; \
    npm --version; \
    install_attempt=1; \
    while ! npm ci --include=dev --no-audit --no-fund --prefer-offline --registry="${NPM_CONFIG_REGISTRY}"; do \
      find /root/.npm/_logs -maxdepth 1 -type f -name '*.log' -print -exec tail -n 80 {} \; 2>/dev/null || true; \
      if [ "$install_attempt" -ge 3 ]; then \
        echo "npm ci failed after ${install_attempt} attempts" >&2; \
        exit 1; \
      fi; \
      rm -rf node_modules; \
      npm cache verify || true; \
      sleep $((install_attempt * 15)); \
      install_attempt=$((install_attempt + 1)); \
    done; \
    test -x node_modules/.bin/tsc; \
    test -x node_modules/.bin/next

FROM node:20-bookworm-slim AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1 NODE_ENV=production
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ARG NEXT_PUBLIC_OPENEDX_CMS_BASE_URL=http://studio.local.openedx.io
ARG NEXT_PUBLIC_AUTO_CMS_SESSION_LOGIN=true
ARG NEXT_PUBLIC_APP_ENV=production
ARG NEXT_PUBLIC_ENABLE_DIAGNOSTICS_UI=false
ARG NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.64.16.5.7.2.9
ARG NEXT_PUBLIC_API_GET_TIMEOUT_MS=45000
ARG FRONTEND_VALIDATE_IN_IMAGE=false
ARG NEXT_PUBLIC_API_WRITE_TIMEOUT_MS=120000
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL} \
    NEXT_PUBLIC_OPENEDX_CMS_BASE_URL=${NEXT_PUBLIC_OPENEDX_CMS_BASE_URL} \
    NEXT_PUBLIC_AUTO_CMS_SESSION_LOGIN=${NEXT_PUBLIC_AUTO_CMS_SESSION_LOGIN} \
    NEXT_PUBLIC_APP_ENV=${NEXT_PUBLIC_APP_ENV} \
    NEXT_PUBLIC_ENABLE_DIAGNOSTICS_UI=${NEXT_PUBLIC_ENABLE_DIAGNOSTICS_UI} \
    NEXT_PUBLIC_APP_VERSION=${NEXT_PUBLIC_APP_VERSION} \
    NEXT_PUBLIC_API_GET_TIMEOUT_MS=${NEXT_PUBLIC_API_GET_TIMEOUT_MS} \
    NEXT_PUBLIC_API_WRITE_TIMEOUT_MS=${NEXT_PUBLIC_API_WRITE_TIMEOUT_MS} \
    FRONTEND_VALIDATE_IN_IMAGE=${FRONTEND_VALIDATE_IN_IMAGE}
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN if [ "${FRONTEND_VALIDATE_IN_IMAGE}" = "true" ]; then npm run lint && npm run typecheck; fi \
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
