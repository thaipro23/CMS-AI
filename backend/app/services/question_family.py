from __future__ import annotations

import hashlib
import re
import unicodedata


def _strip_vietnamese(value: str) -> str:
    normalized = unicodedata.normalize('NFD', value or '')
    return ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Mn')


def slugify(value: object, *, max_len: int = 80) -> str:
    text = _strip_vietnamese(str(value or '').strip().lower())
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    text = re.sub(r'-{2,}', '-', text)
    if not text:
        text = 'concept'
    return text[:max_len].strip('-') or 'concept'


def short_hash(value: object, *, length: int = 8) -> str:
    return hashlib.sha1(str(value or '').encode('utf-8')).hexdigest()[:length]


def normalize_difficulty(value: object) -> str:
    text = str(value or 'easy').strip().lower()
    if text in {'easy', 'medium', 'hard'}:
        return text
    return 'easy'


def build_question_family_id(
    *,
    course_id: str,
    difficulty: str,
    concept_id: str | None = None,
    concept_key: str | None = None,
    concept_title: str | None = None,
    source_node_id: str | None = None,
    source_chunk_id: str | None = None,
    question_text: str | None = None,
) -> str:
    """Return a stable family id for concept-aware variants.

    v25.9.14.1 rule: one concept + one difficulty = one family. If the model
    did not return a concept, fallback to source node/chunk and a short hash so
    old/mock flows still get a usable family id instead of null.
    """
    diff = normalize_difficulty(difficulty)
    course_slug = slugify(course_id.split('+')[1] if '+' in course_id else course_id, max_len=24)
    if concept_key:
        concept_part = slugify(concept_key, max_len=72)
    elif concept_title:
        concept_part = slugify(concept_title, max_len=72)
    elif concept_id:
        concept_part = slugify(concept_id, max_len=72)
    else:
        seed = source_node_id or source_chunk_id or question_text or course_id
        concept_part = f'source-{slugify(seed, max_len=36)}-{short_hash(seed)}'
    return f'{course_slug}-{concept_part}-{diff}'[:180].strip('-')


def normalize_family_id(value: object | None, **fallback_kwargs) -> str:
    text = str(value or '').strip().strip('"').strip("'")
    text = slugify(text, max_len=180) if text else ''
    if text:
        return text
    return build_question_family_id(**fallback_kwargs)
