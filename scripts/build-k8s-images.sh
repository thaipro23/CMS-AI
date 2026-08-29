#!/usr/bin/env sh
set -eu

VERSION="${VERSION:-25.9.16.7.2.64.16.5.7.2.18}"
REGISTRY="${REGISTRY:?Set REGISTRY, e.g. registry.example.com/fpt}"
BACKEND_IMAGE="${BACKEND_IMAGE:-${REGISTRY}/ai-server-backend:${VERSION}}"
FRONTEND_IMAGE="${FRONTEND_IMAGE:-${REGISTRY}/ai-server-frontend:${VERSION}}"

: "${NEXT_PUBLIC_API_BASE_URL:?Set NEXT_PUBLIC_API_BASE_URL}"
: "${NEXT_PUBLIC_OPENEDX_CMS_BASE_URL:?Set NEXT_PUBLIC_OPENEDX_CMS_BASE_URL}"

printf 'Building backend: %s\n' "$BACKEND_IMAGE"
docker build \
  -f backend/Dockerfile.prod \
  -t "$BACKEND_IMAGE" \
  .

printf 'Building frontend: %s\n' "$FRONTEND_IMAGE"
docker build \
  -f frontend/Dockerfile \
  --build-arg "NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}" \
  --build-arg "NEXT_PUBLIC_OPENEDX_CMS_BASE_URL=${NEXT_PUBLIC_OPENEDX_CMS_BASE_URL}" \
  --build-arg "NEXT_PUBLIC_AUTO_CMS_SESSION_LOGIN=${NEXT_PUBLIC_AUTO_CMS_SESSION_LOGIN:-true}" \
  --build-arg "NEXT_PUBLIC_APP_ENV=${NEXT_PUBLIC_APP_ENV:-production}" \
  --build-arg "NEXT_PUBLIC_ENABLE_DIAGNOSTICS_UI=${NEXT_PUBLIC_ENABLE_DIAGNOSTICS_UI:-false}" \
  --build-arg "NEXT_PUBLIC_APP_VERSION=${VERSION}" \
  --build-arg "FRONTEND_VALIDATE_IN_IMAGE=${FRONTEND_VALIDATE_IN_IMAGE:-true}" \
  -t "$FRONTEND_IMAGE" \
  frontend

if [ "${PUSH:-false}" = "true" ]; then
  docker push "$BACKEND_IMAGE"
  docker push "$FRONTEND_IMAGE"
fi

printf '\nOnly two custom application images are produced:\n- %s\n- %s\n' "$BACKEND_IMAGE" "$FRONTEND_IMAGE"
