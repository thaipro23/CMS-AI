from __future__ import annotations

import re
from typing import Iterable, TypeVar

from sqlalchemy.orm import Session

from app.models.course import ContentChunk

T = TypeVar('T')


def split_source_chunk_ids(value: object) -> list[str]:
    """Normalize model-returned source_chunk_id into individual chunk ids.

    LLM sometimes returns multiple supporting chunks in one field, e.g.
    "chunkA;chunkB" or "chunkA, chunkB". Older code treated that as one
    primary key and raised invalid_source_chunk even though each chunk exists.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        parts: list[str] = []
        for item in value:
            parts.extend(split_source_chunk_ids(item))
        return _dedupe(parts)
    text = str(value).strip()
    if not text:
        return []
    # Keep slash in ids such as materialVersion/page33, but split common multi-id separators.
    parts = [p.strip() for p in re.split(r'\s*(?:;|,|\||\n)\s*', text) if p and p.strip()]
    return _dedupe(parts)


def join_source_chunk_ids(ids: Iterable[str]) -> str | None:
    values = _dedupe([str(x).strip() for x in ids if str(x or '').strip()])
    return ';'.join(values) if values else None


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def get_existing_content_chunks(db: Session, source_chunk_id: object) -> list[ContentChunk]:
    ids = split_source_chunk_ids(source_chunk_id)
    if not ids:
        return []
    chunks: list[ContentChunk] = []
    for chunk_id in ids:
        chunk = db.get(ContentChunk, chunk_id)
        if chunk:
            chunks.append(chunk)
    return chunks


def get_missing_content_chunk_ids(db: Session, source_chunk_id: object) -> list[str]:
    ids = split_source_chunk_ids(source_chunk_id)
    if not ids:
        return []
    existing = {chunk.id for chunk in get_existing_content_chunks(db, ids)}
    return [chunk_id for chunk_id in ids if chunk_id not in existing]


def first_existing_content_chunk(db: Session, source_chunk_id: object) -> ContentChunk | None:
    chunks = get_existing_content_chunks(db, source_chunk_id)
    return chunks[0] if chunks else None
