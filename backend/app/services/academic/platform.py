from __future__ import annotations

from typing import Any

from sqlalchemy import or_

from app.models.academic import AcademicSubjectDelivery


def cms_delivery_predicate(delivery: Any = AcademicSubjectDelivery):
    """Treat an absent or unset delivery as the legacy/default CMS platform."""
    return or_(
        delivery.id.is_(None),
        delivery.learning_platform.is_(None),
        delivery.learning_platform == 'cms',
    )
