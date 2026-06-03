from __future__ import annotations

from dataclasses import dataclass, field
import re
from difflib import SequenceMatcher
from sqlalchemy.orm import Session

from app.models.course import ContentChunk

FORBIDDEN_PATTERNS = [
    'không phải là không',
    'ngoại trừ',
    'tất cả đều sai',
    'tất cả các đáp án trên',
    'đâu không phải là không',
]


@dataclass
class QualityResult:
    passed: bool
    reason: str = 'OK'
    flags: list[str] | None = None
    score: float = 1.0
    error_code: str | None = None
    detail: dict = field(default_factory=dict)


class QualityChecker:
    def __init__(self, db: Session | None = None):
        self.db = db

    def _fail(self, code: str, reason: str, *, score: float = 0.0, detail: dict | None = None) -> QualityResult:
        return QualityResult(False, reason, [code], score, code, detail or {})

    def check(self, item: dict) -> QualityResult:
        flags: list[str] = []
        question = (item.get('question') or item.get('question_text') or '').strip()
        question_lower = question.lower()
        options = item.get('options') or {
            'A': item.get('option_a'),
            'B': item.get('option_b'),
            'C': item.get('option_c'),
            'D': item.get('option_d'),
        }
        correct = item.get('correct_answer')
        source_ref = item.get('source_ref') or (item.get('source') or {}).get('ref')
        source_chunk_id = item.get('source_chunk_id') or (item.get('source') or {}).get('chunk_id')

        if not question or len(question) < 10:
            return self._fail('missing_question', 'Thiếu câu hỏi hoặc câu hỏi quá ngắn.')
        if len([v for v in options.values() if str(v or '').strip()]) != 4:
            return self._fail('missing_options', 'Thiếu câu hỏi hoặc không đủ 4 đáp án.', detail={'non_empty_options': len([v for v in options.values() if str(v or '').strip()])})
        if correct not in {'A', 'B', 'C', 'D'}:
            return self._fail('invalid_answer', 'Đáp án đúng không hợp lệ.', detail={'correct_answer': correct})
        if not item.get('explanation'):
            flags.append('missing_explanation')
        if not source_ref and not source_chunk_id:
            flags.append('missing_source_reference')
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in question_lower:
                return self._fail('anti_trick', f'Vi phạm anti-trick rule: {pattern}', detail={'pattern': pattern})
        if 'không' in question_lower and question_lower.count('không') >= 2:
            return self._fail('double_negative', 'Câu hỏi có dấu hiệu phủ định kép.', detail={'khong_count': question_lower.count('không')})

        normalized_options = [str(v or '').strip().lower() for v in options.values()]
        if len(set(normalized_options)) < 4:
            return self._fail('duplicate_options', 'Đáp án bị trùng hoặc quá giống nhau.')
        similar_pair = self._answers_too_similar(normalized_options)
        if similar_pair:
            return self._fail('similar_options', 'Các đáp án quá giống nhau, dễ gây đánh đố.', detail={'pair': similar_pair})
        problem_source_text = ''
        if self.db and source_chunk_id:
            chunk = self.db.get(ContentChunk, source_chunk_id)
            if not chunk:
                return self._fail('invalid_source_chunk', 'Source chunk không tồn tại trong dữ liệu đã sync.', detail={'source_chunk_id': source_chunk_id})
            if (chunk.source_type or '').lower() == 'problem':
                problem_source_text = chunk.content or ''
        if not problem_source_text and str(item.get('source_type') or '').lower() == 'problem':
            problem_source_text = item.get('source_excerpt') or ''
        if problem_source_text:
            copied = self._copied_old_problem_question(question, problem_source_text)
            if copied:
                return self._fail(
                    'old_problem_copy',
                    'Câu hỏi sinh ra quá giống câu hỏi cũ trong CMS. Cần đổi cách hỏi, đổi góc hỏi hoặc viết lại bằng ngữ cảnh khác.',
                    score=0.2,
                    detail=copied,
                )

        score = max(0.0, 1.0 - 0.15 * len(flags))
        passed = score >= 0.7
        return QualityResult(
            passed,
            'OK' if passed else ', '.join(flags),
            flags,
            score,
            None if passed else 'quality_score_low',
            {'warnings': flags},
        )

    def _normalize_for_similarity(self, value: str) -> str:
        value = (value or '').lower()
        value = re.sub(r'\[đáp án đúng\]', ' ', value)
        value = re.sub(r'[^0-9a-zà-ỹ]+', ' ', value, flags=re.IGNORECASE)
        value = re.sub(r'\s+', ' ', value).strip()
        return value

    def _extract_old_problem_questions(self, source_text: str) -> list[str]:
        questions: list[str] = []
        for line in (source_text or '').splitlines():
            cleaned = line.strip()
            match = re.match(r'^(?:câu|question)\s*\d+\s*[:.)-]\s*(.+)$', cleaned, flags=re.IGNORECASE)
            if match:
                question = match.group(1).strip()
                if question:
                    questions.append(question)
        return questions

    def _copied_old_problem_question(self, generated_question: str, source_text: str) -> dict | None:
        generated = self._normalize_for_similarity(generated_question)
        if not generated:
            return None
        for old_question in self._extract_old_problem_questions(source_text):
            old = self._normalize_for_similarity(old_question)
            if len(old) < 12:
                continue
            ratio = SequenceMatcher(None, generated, old).ratio()
            # High threshold avoids blocking same concept, while still catching
            # direct copies or almost-direct rewrites of the old CMS quiz item.
            if ratio >= 0.82 or generated == old or generated in old or old in generated:
                return {
                    'similarity': round(ratio, 4),
                    'old_question': old_question[:240],
                    'generated_question': generated_question[:240],
                }
        return None

    def _answers_too_similar(self, options: list[str]) -> list[str] | None:
        for i, left in enumerate(options):
            for j, right in enumerate(options[i + 1:], start=i + 1):
                if left and right and SequenceMatcher(None, left, right).ratio() > 0.86:
                    return [chr(ord('A') + i), chr(ord('A') + j)]
        return None
