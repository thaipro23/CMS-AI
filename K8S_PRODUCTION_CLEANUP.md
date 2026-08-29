# K8s production cleanup — v25.9.16.7.2.64.16.5.7.2.10-k8s-r1

This package keeps application behavior at v25.9.16.7.2.64.16.5.7.2.10 and changes only production packaging/deployment.

## Custom images
Only two custom application images are built:

1. `ai-server-backend:<version>` — reused by API, migrate Job, Celery interactive/sync worker, heavy worker, analytics worker and beat.
2. `ai-server-frontend:<version>` — Next.js standalone runtime.

PostgreSQL, Redis, Prometheus and Grafana are dependencies/optional platform services; they are not custom AI Server images and are not built from this repository for K8s.

## Removed from production-clean package

- screenshot evidence under `docs/evidence`
- historical docs under `docs/history`
- GitHub CI metadata
- Playwright/e2e package
- separate Learning MFE patch (not part of AI Server K8s images)
- old project-context/handoff/release/run/verification files
- cache/log/private-key artifacts

The Open edX connector and unit-reset plugin source are intentionally retained because production readiness/security diagnostics inspect their source contract.

## Build

```bash
export REGISTRY=registry.example.com/fpt
export NEXT_PUBLIC_API_BASE_URL=https://api-ai.cms.fpt.edu.vn
export NEXT_PUBLIC_OPENEDX_CMS_BASE_URL=https://scms.fpt.edu.vn
export PUSH=true
./scripts/build-k8s-images.sh
```

## Secret

Reuse the existing `.env.production` values as a K8s Secret. Do not commit the generated Secret YAML:

```bash
kubectl -n openedx create secret generic ai-server-env \
  --from-env-file=.env.production \
  --dry-run=client -o yaml | kubectl apply -f -
```

## Set registry/version in Kustomize

```bash
cd deploy/k8s/base
kustomize edit set image \
  ai-server-backend=REGISTRY/ai-server-backend:25.9.16.7.2.64.16.5.7.2.10 \
  ai-server-frontend=REGISTRY/ai-server-frontend:25.9.16.7.2.64.16.5.7.2.10
```

Adjust namespace and the `ai-server-runtime` PVC storage class/access mode for the cluster before applying. The default manifests request RWX because API/workers share runtime import/export files.

Run migration as a one-shot Job before rolling the workloads. Do not run multiple migration Jobs concurrently.
