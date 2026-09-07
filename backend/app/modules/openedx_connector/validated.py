from __future__ import annotations

from typing import Any

from app.modules.openedx_connector.real import RealOpenEdXConnector
from app.services.problem_bank_slot_metadata import normalize_problem_bank_slots


class ValidatedRealOpenEdXConnector(RealOpenEdXConnector):
    """Real connector with a strict Problem Bank slot metadata boundary."""

    async def insert_problem_banks(
        self,
        course_id: str,
        unit_node_id: str,
        slots: list[dict[str, Any]],
        metadata: dict | None = None,
    ) -> dict:
        return await super().insert_problem_banks(
            course_id=course_id,
            unit_node_id=unit_node_id,
            slots=normalize_problem_bank_slots(slots),
            metadata=metadata,
        )
