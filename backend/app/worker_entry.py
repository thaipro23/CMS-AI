from __future__ import annotations

# Compatibility import for deployments/scripts that adopted worker_entry during
# the runtime split. The canonical Celery app and all runtime registrations now
# live in app.worker so existing Jenkins/Kubernetes commands can continue using:
#   celery -A app.worker.celery_app ...
from app.worker import celery_app

__all__ = ['celery_app']
