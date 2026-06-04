from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from sqlalchemy.orm import Session

from app.models.concept import Concept
from app.models.course import ContentChunk, CourseSyncState
from app.services.token_counter import count_tokens


STOPWORDS = {
    'the', 'and', 'for', 'with', 'from', 'that', 'this', 'are', 'will', 'can',
    'của', 'và', 'cho', 'trong', 'khi', 'được', 'các', 'một', 'những', 'với',
    'theo', 'nội', 'dung', 'bài', 'học', 'sinh', 'viên', 'hiểu', 'biết', 'câu',
    'hỏi', 'đáp', 'án', 'đúng', 'không', 'là', 'có', 'để', 'về', 'này', 'đó',
}


@dataclass
class ConceptCandidate:
    title: str
    summary: str
    learning_objective: str
    difficulty_hint: str
    importance_score: float
    source_chunk_ids: list[str]
    source_evidence: str
    token_count: int
    metadata: dict


def _strip_accents(value: str) -> str:
    value = unicodedata.normalize('NFKD', value or '')
    return ''.join(ch for ch in value if not unicodedata.combining(ch))


def _slug(value: str, max_len: int = 90) -> str:
    value = _strip_accents(value).lower()
    value = re.sub(r'[^a-z0-9]+', '-', value).strip('-')
    value = re.sub(r'-+', '-', value)
    return (value[:max_len].strip('-') or 'concept')


def _clean_text(value: str) -> str:
    value = re.sub(r'<[^>]+>', ' ', value or '')
    value = re.sub(r'\[ĐÁP ÁN ĐÚNG\]', ' ', value, flags=re.IGNORECASE)
    value = re.sub(r'\s+', ' ', value).strip()
    return value


def _sentences(text: str) -> list[str]:
    cleaned = _clean_text(text)
    parts = re.split(r'(?<=[.!?。])\s+|\n+|\s{2,}', cleaned)
    out: list[str] = []
    for part in parts:
        item = part.strip(' -•\t')
        if 35 <= len(item) <= 260:
            out.append(item)
    return out


def _keywords(text: str, limit: int = 8) -> list[str]:
    words = re.findall(r'[A-Za-zÀ-ỹ0-9]{3,}', (text or '').lower())
    counts: dict[str, int] = {}
    for word in words:
        norm = _strip_accents(word)
        if norm in STOPWORDS or len(norm) < 3:
            continue
        counts[word] = counts.get(word, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]


def _title_from_sentence(sentence: str, fallback_title: str) -> str:
    sentence = _clean_text(sentence)
    # Remove leading question/order markers from old quizzes.
    sentence = re.sub(r'^(?:câu|question)\s*\d+\s*[:.)-]\s*', '', sentence, flags=re.IGNORECASE)
    sentence = re.sub(r'^(?:theo|trong)\s+', '', sentence, flags=re.IGNORECASE)
    if len(sentence) <= 72:
        return sentence.rstrip('?.!')
    keywords = _keywords(sentence, 5)
    if keywords:
        title = ' / '.join(word[:35] for word in keywords[:4])
        return title[:90]
    return (fallback_title or sentence[:72]).rstrip('?.!')


def _difficulty_hint(text: str, source_type: str | None = None) -> str:
    lower = (text or '').lower()
    if any(k in lower for k in ['phân tích', 'so sánh', 'tối ưu', 'kết hợp', 'trường hợp', 'tình huống', 'áp dụng', 'vì sao']):
        return 'medium'
    if any(k in lower for k in ['thiết kế', 'triển khai', 'xử lý', 'đánh giá', 'quyết định', 'lựa chọn phù hợp']):
        return 'hard'
    if (source_type or '').lower() in {'problem', 'quiz'}:
        return 'easy'
    return 'easy'


def _concept_key(title: str, source_node_id: str | None) -> str:
    base = _slug(title, 80)
    digest = hashlib.sha1(f'{source_node_id or "course"}|{title}'.encode('utf-8')).hexdigest()[:8]
    return f'{base}-{digest}'


class ConceptService:
    def __init__(self, db: Session):
        self.db = db

    def list_concepts(self, course_id: str, node_id: str | None = None, status: str = 'active') -> list[Concept]:
        query = self.db.query(Concept).filter(Concept.course_id == course_id)
        if node_id and node_id != 'all':
            query = query.filter(Concept.source_node_id == node_id)
        if status:
            query = query.filter(Concept.status == status)
        return query.order_by(Concept.importance_score.desc(), Concept.created_at.asc()).all()

    def extract_for_chunks(
        self,
        *,
        course_id: str,
        chunks: list[ContentChunk],
        node_id: str | None,
        node_title: str | None = None,
        max_concepts: int = 20,
        force: bool = False,
    ) -> tuple[list[Concept], bool]:
        existing = self.list_concepts(course_id, node_id)
        if existing and not force:
            return existing[:max_concepts], True

        if force and node_id:
            self.db.query(Concept).filter(Concept.course_id == course_id, Concept.source_node_id == node_id).delete(synchronize_session=False)
            self.db.flush()

        candidates = self._build_candidates(chunks, node_title=node_title, max_concepts=max_concepts)
        concepts: list[Concept] = []
        chapter_node_id = self._resolve_chapter_node_id(course_id, node_id)
        for candidate in candidates:
            key = _concept_key(candidate.title, node_id)
            existing_row = self.db.query(Concept).filter(
                Concept.course_id == course_id,
                Concept.source_node_id == node_id,
                Concept.concept_key == key,
            ).first()
            row = existing_row or Concept(course_id=course_id, source_node_id=node_id, concept_key=key)
            row.chapter_node_id = chapter_node_id
            row.source_node_title = node_title or self._node_title(course_id, node_id)
            row.title = candidate.title[:512]
            row.summary = candidate.summary
            row.learning_objective = candidate.learning_objective
            row.difficulty_hint = candidate.difficulty_hint
            row.importance_score = float(candidate.importance_score)
            row.source_chunk_ids = candidate.source_chunk_ids
            row.source_evidence = candidate.source_evidence
            row.token_count = int(candidate.token_count or 0)
            row.status = 'active'
            row.metadata_json = candidate.metadata
            self.db.add(row)
            concepts.append(row)
        self.db.commit()
        for concept in concepts:
            self.db.refresh(concept)
        return concepts, False

    def _node_title(self, course_id: str, node_id: str | None) -> str | None:
        if not node_id:
            return None
        state = self.db.query(CourseSyncState).filter(CourseSyncState.course_id == course_id, CourseSyncState.block_id == node_id).first()
        return state.display_name if state else None

    def _resolve_chapter_node_id(self, course_id: str, node_id: str | None) -> str | None:
        if not node_id:
            return None
        states = {row.block_id: row for row in self.db.query(CourseSyncState).filter(CourseSyncState.course_id == course_id).all()}
        current = states.get(node_id)
        seen = set()
        while current and current.block_id not in seen:
            seen.add(current.block_id)
            if (current.block_type or '').lower() in {'chapter', 'sequential'}:
                return current.block_id
            current = states.get(current.parent_block_id or '')
        return node_id

    def _build_candidates(self, chunks: list[ContentChunk], *, node_title: str | None, max_concepts: int) -> list[ConceptCandidate]:
        buckets: dict[str, ConceptCandidate] = {}
        for chunk in chunks:
            chunk_sentences = _sentences(chunk.content)[:8]
            if not chunk_sentences and chunk.content:
                chunk_sentences = [_clean_text(chunk.content)[:220]]
            for sentence in chunk_sentences:
                title = _title_from_sentence(sentence, node_title or 'Nội dung bài học')
                if len(title) < 8:
                    continue
                base_key = _slug(title, 64)
                keywords = _keywords(sentence, 8)
                summary = sentence[:500]
                objective = f'Sinh viên hiểu và vận dụng được nội dung: {title}.'
                score = min(1.0, 0.35 + 0.04 * len(keywords) + min(len(sentence), 220) / 500)
                if (chunk.source_type or '').lower() in {'problem', 'quiz'}:
                    score += 0.05
                score = max(0.05, min(score, 1.0))
                existing = buckets.get(base_key)
                if existing:
                    existing.importance_score = max(existing.importance_score, score)
                    if chunk.id not in existing.source_chunk_ids:
                        existing.source_chunk_ids.append(chunk.id)
                    if len(existing.source_evidence) < len(summary):
                        existing.source_evidence = summary
                    existing.token_count += int(chunk.token_count or 0)
                    existing.metadata.setdefault('keywords', [])
                    for keyword in keywords:
                        if keyword not in existing.metadata['keywords']:
                            existing.metadata['keywords'].append(keyword)
                    continue
                buckets[base_key] = ConceptCandidate(
                    title=title,
                    summary=summary,
                    learning_objective=objective,
                    difficulty_hint=_difficulty_hint(sentence, chunk.source_type),
                    importance_score=score,
                    source_chunk_ids=[chunk.id],
                    source_evidence=summary,
                    token_count=int(chunk.token_count or count_tokens(sentence)),
                    metadata={'keywords': keywords, 'source_type': chunk.source_type, 'source_ref': chunk.source_ref},
                )
        candidates = sorted(buckets.values(), key=lambda c: (-c.importance_score, c.title.lower()))
        return candidates[:max_concepts]


def format_concepts_for_prompt(concepts: list[Concept], max_items: int = 12) -> str:
    active = [c for c in concepts if c and (c.status or 'active') == 'active'][:max_items]
    if not active:
        return ''
    lines = [
        'Concept-aware generation hints:',
        'Các concept dưới đây là các vấn đề học tập riêng biệt. Khi tạo câu hỏi, hãy phân bổ câu hỏi qua nhiều concept khác nhau, không tạo nhiều câu cùng một gốc nội dung trong cùng batch nếu không cần biến thể.',
    ]
    for idx, concept in enumerate(active, start=1):
        lines.append(
            f'{idx}. concept_id={concept.id}; title={concept.title}; difficulty_hint={concept.difficulty_hint}; '
            f'learning_objective={concept.learning_objective}; evidence={concept.source_evidence[:220]}'
        )
    lines.append('Mỗi câu hỏi trong JSON nên điền concept_id và concept_title khớp một concept ở trên nếu phù hợp.')
    return '\n'.join(lines)
