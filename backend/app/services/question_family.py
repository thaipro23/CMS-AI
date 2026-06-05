from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from typing import Any

from app.models.question import Question


STABLE_FAMILY_RE = re.compile(r'^fam-v1-[0-9a-f]{16}-(easy|medium|hard)$', re.IGNORECASE)


def is_stable_family_id(value: object) -> bool:
    return bool(STABLE_FAMILY_RE.fullmatch(str(value or '').strip().strip('\"\'')))


def _legacy_family_root(value: object) -> str:
    text = str(value or '').strip().strip('\"\'').casefold()
    if not text or is_stable_family_id(text):
        return ''
    text = re.sub(r'^(?:cf|fam)-', '', text)
    text = re.sub(r'-(?:easy|medium|hard)(?:-\d+)?$', '', text)
    return normalize_identity_text(text)


def normalize_difficulty(value: object) -> str:
    text = str(value or 'easy').strip().lower()
    return text if text in {'easy', 'medium', 'hard'} else 'easy'


def normalize_identity_text(value: object) -> str:
    """Normalize concept identity while preserving Vietnamese meaning."""
    text = unicodedata.normalize('NFKC', str(value or '')).casefold()
    text = re.sub(r'[^\w\s]+', ' ', text, flags=re.UNICODE)
    return re.sub(r'\s+', ' ', text).strip()


def canonical_concept_identity(
    *,
    concept_key: str | None = None,
    concept_id: str | None = None,
    concept_title: str | None = None,
    legacy_family_id: str | None = None,
    topic: str | None = None,
    learning_objective: str | None = None,
    source_node_id: str | None = None,
    source_chunk_id: str | None = None,
    question_text: str | None = None,
) -> tuple[str, str]:
    """Return the authoritative concept identity produced before planning.

    GPT/concept extraction already determines the concept. Planning never sends
    questions to GPT again. The stored concept_id/concept_key are authoritative.
    Legacy family roots are only used when those links are absent; visible titles
    are a last-resort fallback because two different concepts may share a title.
    """
    normalized_concept_id = normalize_identity_text(concept_id)
    if normalized_concept_id:
        return 'concept_id', normalized_concept_id
    normalized_concept_key = normalize_identity_text(concept_key)
    if normalized_concept_key:
        return 'concept_key', normalized_concept_key

    legacy = _legacy_family_root(legacy_family_id)
    if legacy:
        return 'legacy_family_root', legacy

    # Title fallback is scoped by the source node where possible to avoid
    # collapsing unrelated concepts that happen to have the same display name.
    normalized_title = normalize_identity_text(concept_title)
    if normalized_title:
        source_scope = normalize_identity_text(source_node_id or source_chunk_id or '')
        return 'concept_title', f'{source_scope}|{normalized_title}' if source_scope else normalized_title

    candidates = (
        ('topic', topic),
        ('learning_objective', learning_objective),
        ('source_node_id', source_node_id),
        ('source_chunk_id', source_chunk_id),
        ('question_text', question_text),
    )
    for source, value in candidates:
        normalized = normalize_identity_text(value)
        if normalized:
            return source, normalized
    return 'fallback', 'unknown-concept'


def build_question_family_id(
    *,
    course_id: str,
    difficulty: str,
    chapter_node_id: str | None = None,
    concept_id: str | None = None,
    concept_key: str | None = None,
    concept_title: str | None = None,
    legacy_family_id: str | None = None,
    topic: str | None = None,
    learning_objective: str | None = None,
    source_node_id: str | None = None,
    source_chunk_id: str | None = None,
    question_text: str | None = None,
) -> str:
    """Build one stable family ID for one concept + difficulty in one chapter.

    Variant number and question ID are deliberately excluded. Stored concept
    links are authoritative; a normalized legacy family root is only a fallback
    for old rows without concept metadata. This fixes IDs such as
    fam-...-easy-1/-2/-3 that falsely represented variants as separate families.
    """
    diff = normalize_difficulty(difficulty)
    existing = str(legacy_family_id or '').strip().strip('\"\'').casefold()
    # Preserve a previously reconciled backend-owned family when the row has no
    # stronger stored concept link. This makes preview reconciliation idempotent.
    if is_stable_family_id(existing) and not normalize_identity_text(concept_id) and not normalize_identity_text(concept_key):
        if existing.endswith(f'-{diff}'):
            return existing
    source, identity = canonical_concept_identity(
        concept_key=concept_key,
        concept_id=concept_id,
        concept_title=concept_title,
        legacy_family_id=legacy_family_id,
        topic=topic,
        learning_objective=learning_objective,
        source_node_id=source_node_id,
        source_chunk_id=source_chunk_id,
        question_text=question_text,
    )
    seed = '|'.join((
        normalize_identity_text(course_id),
        normalize_identity_text(chapter_node_id or ''),
        source,
        identity,
        diff,
    ))
    digest = hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]
    return f'fam-v1-{digest}-{diff}'


def normalize_family_id(value: object | None = None, **fallback_kwargs: Any) -> str:
    """Return the backend-authoritative stable family ID.

    ``value`` is accepted for backward-compatible callers only as a normalized
    legacy fallback. Existing concept_id/concept_key still take precedence.
    """
    if value and not fallback_kwargs.get('legacy_family_id'):
        fallback_kwargs['legacy_family_id'] = str(value)
    return build_question_family_id(**fallback_kwargs)


def stable_family_id_for_question(question: Question) -> str:
    return build_question_family_id(
        course_id=str(getattr(question, 'course_id', '') or ''),
        chapter_node_id=getattr(question, 'chapter_node_id', None),
        difficulty=str(getattr(question, 'difficulty', '') or 'easy'),
        concept_id=getattr(question, 'concept_id', None),
        concept_key=getattr(question, 'concept_key', None),
        concept_title=getattr(question, 'concept_title', None),
        legacy_family_id=getattr(question, 'question_family_id', None),
        topic=getattr(question, 'topic', None),
        learning_objective=getattr(question, 'learning_objective', None),
        source_node_id=getattr(question, 'source_node_id', None),
        source_chunk_id=getattr(question, 'source_chunk_id', None),
        question_text=getattr(question, 'question_text', None),
    )


def stable_family_name(question: Question) -> str:
    value = (
        getattr(question, 'concept_title', None)
        or getattr(question, 'topic', None)
        or getattr(question, 'learning_objective', None)
        or getattr(question, 'source_node_title', None)
        or stable_family_id_for_question(question)
    )
    return re.sub(r'\s+', ' ', str(value or '').strip())[:120]


def reconcile_question_families(
    db: Any,
    course_id: str,
    *,
    chapter_node_id: str | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    """Backfill stable family IDs and deterministic variant numbers.

    This function is intentionally deterministic and does not call a model. It
    is run before plan preview and is also mirrored by Alembic migration 0008.
    """
    query = db.query(Question).filter(Question.course_id == course_id)
    if chapter_node_id:
        query = query.filter(Question.chapter_node_id == chapter_node_id)
    questions = list(query.all())

    before_ids = {str(getattr(question, 'question_family_id', '') or '') for question in questions}
    grouped: dict[str, list[Question]] = defaultdict(list)
    updated_question_count = 0
    changes: list[dict[str, str]] = []

    for question in questions:
        old_id = str(getattr(question, 'question_family_id', '') or '')
        new_id = stable_family_id_for_question(question)
        if old_id != new_id:
            question.question_family_id = new_id
            updated_question_count += 1
            if len(changes) < 50:
                changes.append({'question_id': str(question.id), 'old_family_id': old_id, 'new_family_id': new_id})
        grouped[new_id].append(question)

    variant_no_updated_count = 0
    for family_id, members in grouped.items():
        members.sort(key=lambda question: (
            str(getattr(question, 'created_at', '') or ''),
            str(question.id),
        ))
        for variant_no, question in enumerate(members, start=1):
            if int(getattr(question, 'variant_no', 0) or 0) != variant_no:
                question.variant_no = variant_no
                variant_no_updated_count += 1
            question.question_family_id = family_id

    if commit and hasattr(db, 'commit'):
        db.commit()
    elif hasattr(db, 'flush'):
        db.flush()

    after_ids = set(grouped)
    return {
        'strategy': 'course+chapter+concept_identity+difficulty',
        'uses_llm': False,
        'question_count': len(questions),
        'family_count_before': len(before_ids - {''}),
        'family_count_after': len(after_ids),
        'merged_family_count': max(len(before_ids - {''}) - len(after_ids), 0),
        'updated_question_count': updated_question_count,
        'variant_no_updated_count': variant_no_updated_count,
        'sample_changes': changes,
    }
