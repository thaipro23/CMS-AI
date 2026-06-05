"""v25.9.14.5 stable family reconciliation

Revision ID: 0008_v25_9_14_5
Revises: 0007_v25_9_14_1
Create Date: 2026-06-05

Data migration: replace model/legacy family IDs with a backend-authoritative ID
built from course + chapter + existing concept identity + difficulty, then
resequence variant_no inside each stable family. No LLM is called.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict

from alembic import op
import sqlalchemy as sa

revision = '0008_v25_9_14_5'
down_revision = '0007_v25_9_14_1'
branch_labels = None
depends_on = None


_STABLE_FAMILY_RE = re.compile(r'^fam-v1-[0-9a-f]{16}-(easy|medium|hard)$', re.IGNORECASE)


def _normalize(value: object) -> str:
    text = unicodedata.normalize('NFKC', str(value or '')).casefold()
    text = re.sub(r'[^\w\s]+', ' ', text, flags=re.UNICODE)
    return re.sub(r'\s+', ' ', text).strip()


def _difficulty(value: object) -> str:
    value = str(value or 'easy').strip().lower()
    return value if value in {'easy', 'medium', 'hard'} else 'easy'


def _family_id(row: dict) -> str:
    normalized_concept_id = _normalize(row.get('concept_id'))
    normalized_concept_key = _normalize(row.get('concept_key'))
    diff = _difficulty(row.get('difficulty'))
    existing = str(row.get('question_family_id') or '').strip().strip('\"\'').casefold()

    if normalized_concept_id:
        source, identity = 'concept_id', normalized_concept_id
    elif normalized_concept_key:
        source, identity = 'concept_key', normalized_concept_key
    elif _STABLE_FAMILY_RE.fullmatch(existing) and existing.endswith(f'-{diff}'):
        return existing
    else:
        legacy = existing
        legacy = re.sub(r'^(?:cf|fam)-', '', legacy)
        legacy = re.sub(r'-(?:easy|medium|hard)(?:-\d+)?$', '', legacy)
        legacy = _normalize(legacy)
        if legacy:
            source, identity = 'legacy_family_root', legacy
        else:
            title = _normalize(row.get('concept_title'))
            if title:
                scope = _normalize(row.get('source_node_id') or row.get('source_chunk_id') or '')
                source, identity = 'concept_title', f'{scope}|{title}' if scope else title
            else:
                candidates = (
                    ('topic', row.get('topic')),
                    ('learning_objective', row.get('learning_objective')),
                    ('source_node_id', row.get('source_node_id')),
                    ('source_chunk_id', row.get('source_chunk_id')),
                    ('question_text', row.get('question_text')),
                )
                source, identity = 'fallback', 'unknown-concept'
                for candidate_source, value in candidates:
                    normalized = _normalize(value)
                    if normalized:
                        source, identity = candidate_source, normalized
                        break
    seed = '|'.join((
        _normalize(row.get('course_id')),
        _normalize(row.get('chapter_node_id')),
        source,
        identity,
        diff,
    ))
    return f'fam-v1-{hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]}-{diff}'


def upgrade() -> None:
    bind = op.get_bind()
    rows = list(bind.execute(sa.text('''
        SELECT id, course_id, chapter_node_id, concept_key, concept_id,
               concept_title, question_family_id, topic, learning_objective, source_node_id,
               source_chunk_id, question_text, difficulty, created_at
        FROM ai_questions
        ORDER BY created_at NULLS FIRST, id
    ''')).mappings())

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        data = dict(row)
        data['stable_family_id'] = _family_id(data)
        grouped[data['stable_family_id']].append(data)

    update = sa.text('''
        UPDATE ai_questions
        SET question_family_id = :family_id, variant_no = :variant_no
        WHERE id = :id
    ''')
    for family_id, members in grouped.items():
        members.sort(key=lambda row: (str(row.get('created_at') or ''), str(row['id'])))
        for variant_no, row in enumerate(members, start=1):
            bind.execute(update, {'id': row['id'], 'family_id': family_id, 'variant_no': variant_no})

    existing_indexes = {item['name'] for item in sa.inspect(bind).get_indexes('ai_questions')}
    if 'ix_ai_questions_course_chapter_family_difficulty' not in existing_indexes:
        op.create_index(
            'ix_ai_questions_course_chapter_family_difficulty',
            'ai_questions',
            ['course_id', 'chapter_node_id', 'question_family_id', 'difficulty'],
        )


def downgrade() -> None:
    # Stable IDs are a data correction and cannot safely be reconstructed back
    # into inconsistent model/legacy IDs. The supporting index can be removed.
    bind = op.get_bind()
    existing_indexes = {item['name'] for item in sa.inspect(bind).get_indexes('ai_questions')}
    if 'ix_ai_questions_course_chapter_family_difficulty' in existing_indexes:
        op.drop_index('ix_ai_questions_course_chapter_family_difficulty', table_name='ai_questions')
