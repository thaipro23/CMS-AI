"""Compatibility import for older deployments.

The canonical Celery runtime is now app.worker.celery_app. Keep this module so
rolling deployments that still reference app.worker_entry continue to start,
without registering tasks or schedules twice.
"""

from app.worker import celery_app

__all__ = ['celery_app']
