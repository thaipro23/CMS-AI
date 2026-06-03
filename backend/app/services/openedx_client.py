from app.modules.openedx_connector.factory import get_openedx_connector


class OpenEdxClient:
    """Backward-compatible wrapper around the v15 Open edX connector adapters."""

    async def get_course_blocks(self, course_id: str) -> list[dict]:
        return await get_openedx_connector().get_course_blocks(course_id)
