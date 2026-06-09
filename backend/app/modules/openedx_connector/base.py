from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class OpenEdXBlock:
    block_id: str
    type: str
    display_name: str
    data: str = ''
    parent_block_id: str | None = None
    metadata: dict[str, Any] | None = None


class OpenEdXConnector(ABC):
    @abstractmethod
    async def get_course_blocks(self, course_id: str) -> list[dict]:
        """Return normalized course blocks/components for AI sync."""

    @abstractmethod
    async def publish_problem_olx(self, course_id: str, parent_block_id: str | None, olx: str, display_name: str) -> dict:
        """Publish an OLX problem into Open edX or return a dry-run response."""

    async def ensure_problem_library(self, course_id: str, chapter_node_id: str, display_name: str, metadata: dict[str, Any] | None = None) -> dict:
        metadata = metadata or {}
        library_key = metadata.get('library_key') or f'{course_id}:{chapter_node_id}'
        return {
            'course_id': course_id,
            'chapter_node_id': chapter_node_id,
            'library_key': library_key,
            'openedx_library_id': f'library:{library_key}',
            'display_name': display_name,
            'created': False,
            'status': 'local_stub_existing_or_created',
            'tag_names': metadata.get('tag_names') or metadata.get('tags') or [],
            'metadata': metadata,
        }

    async def import_problem_to_library(self, course_id: str, library_key: str, olx: str, display_name: str, metadata: dict[str, Any] | None = None) -> dict:
        result = await self.publish_problem_olx(course_id, None, olx, display_name)
        return {**result, 'metadata': metadata or {}, 'tag_names': (metadata or {}).get('tag_names') or (metadata or {}).get('tags') or []}

    async def verify_library_problem(self, course_id: str, library_key: str, problem_id: str, metadata: dict[str, Any] | None = None) -> dict:
        return {'ok': True, 'status': 'verification_unavailable', 'verified': False, 'manual_check_required': True, 'library_key': library_key, 'problem_id': problem_id, 'metadata': metadata or {}}

    async def delete_library_problem(self, course_id: str, library_key: str, problem_id: str, metadata: dict[str, Any] | None = None) -> dict:
        return {'ok': False, 'status': 'delete_unavailable', 'deleted': False, 'library_key': library_key, 'problem_id': problem_id, 'metadata': metadata or {}}

    async def create_quiz_node(
        self,
        course_id: str,
        parent_node_id: str,
        quiz_title: str,
        unit_title: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        return {
            'ok': False,
            'created': False,
            'status': 'quiz_node_create_unavailable',
            'course_id': course_id,
            'parent_node_id': parent_node_id,
            'quiz_title': quiz_title,
            'unit_title': unit_title,
            'metadata': metadata or {},
        }

    async def delete_quiz_node(self, course_id: str, node_id: str, metadata: dict[str, Any] | None = None) -> dict:
        return {
            'ok': False,
            'deleted': False,
            'status': 'quiz_node_delete_unavailable',
            'course_id': course_id,
            'node_id': node_id,
            'manual_cleanup_required': True,
            'metadata': metadata or {},
        }

    async def insert_problem_banks(
        self,
        course_id: str,
        unit_node_id: str,
        slots: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        return {
            'ok': False,
            'created': False,
            'status': 'problem_bank_insert_unavailable',
            'course_id': course_id,
            'unit_node_id': unit_node_id,
            'problem_bank_blocks': [],
            'slots_requested': len(slots or []),
            'metadata': metadata or {},
        }
