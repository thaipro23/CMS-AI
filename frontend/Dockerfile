# Production-safe Next.js Dockerfile.
# Use Debian slim instead of Alpine because the current package-lock includes
# the glibc Next.js SWC binary (@next/swc-linux-x64-gnu). Alpine lacks
# ld-linux-x86-64.so.2, causing next build to fail on Windows Docker Desktop.
# Important: the deps stage intentionally installs dev dependencies too because
# TypeScript/Next build tools are required during image build. The runtime stage
# only copies Next.js standalone output, so dev dependencies are not shipped.

FROM node:20-bookworm-slim AS deps
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=development
COPY package.json package-lock.json ./
RUN npm ci --include=dev --no-audit --no-fund \
    && test -x node_modules/.bin/tsc \
    && test -x node_modules/.bin/next

FROM node:20-bookworm-slim AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ARG NEXT_PUBLIC_OPENEDX_CMS_BASE_URL=http://studio.local.openedx.io
ARG NEXT_PUBLIC_AUTO_CMS_SESSION_LOGIN=true
ARG NEXT_PUBLIC_APP_ENV=production
ARG NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.64.12
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
ENV NEXT_PUBLIC_OPENEDX_CMS_BASE_URL=${NEXT_PUBLIC_OPENEDX_CMS_BASE_URL}
ENV NEXT_PUBLIC_AUTO_CMS_SESSION_LOGIN=${NEXT_PUBLIC_AUTO_CMS_SESSION_LOGIN}
ENV NEXT_PUBLIC_APP_ENV=${NEXT_PUBLIC_APP_ENV}
ENV NEXT_PUBLIC_APP_VERSION=${NEXT_PUBLIC_APP_VERSION}
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/next build

FROM node:20-bookworm-slim AS runner
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ARG NEXT_PUBLIC_OPENEDX_CMS_BASE_URL=http://studio.local.openedx.io
ARG NEXT_PUBLIC_AUTO_CMS_SESSION_LOGIN=true
ARG NEXT_PUBLIC_APP_ENV=production
ARG NEXT_PUBLIC_APP_VERSION=25.9.16.7.2.64.12
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
ENV NEXT_PUBLIC_OPENEDX_CMS_BASE_URL=${NEXT_PUBLIC_OPENEDX_CMS_BASE_URL}
ENV NEXT_PUBLIC_AUTO_CMS_SESSION_LOGIN=${NEXT_PUBLIC_AUTO_CMS_SESSION_LOGIN}
ENV NEXT_PUBLIC_APP_ENV=${NEXT_PUBLIC_APP_ENV}
ENV NEXT_PUBLIC_APP_VERSION=${NEXT_PUBLIC_APP_VERSION}

# Next.js standalone output contains server.js and the required node_modules subset.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
