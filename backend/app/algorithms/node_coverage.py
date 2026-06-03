from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ContentSignal:
    teachable: bool
    effective_tokens: int
    reason: str


@dataclass
class NodeAllocation:
    node_id: str
    title: str
    block_type: str
    question_quota: int
    chunk_count: int
    token_count: int
    effective_token_count: int = 0
    teachable_chunk_count: int = 0
    skipped_chunk_count: int = 0
    allocation_weight: float = 0.0


_NOISE_PHRASES = [
    # Vietnamese course/admin/intro material that usually should not become questions.
    'giới thiệu môn học', 'giới thiệu khóa học', 'giới thiệu khoá học', 'giới thiệu chung',
    'lời mở đầu', 'mục lục', 'nội dung khóa học', 'nội dung khoá học', 'kế hoạch học tập',
    'đề cương môn học', 'thông tin môn học', 'thông tin khóa học', 'thông tin khoá học',
    'tài liệu tham khảo', 'quy định lớp học', 'quy định môn học', 'hình thức đánh giá',
    'điểm danh', 'chính sách điểm', 'thang điểm', 'lịch học', 'lịch trình học',
    'yêu cầu môn học', 'hướng dẫn sử dụng', 'chào mừng', 'welcome',
    # English equivalents.
    'course introduction', 'course overview', 'welcome to', 'table of contents', 'syllabus',
    'grading policy', 'assessment policy', 'course policy', 'class policy', 'schedule',
    'learning schedule', 'reference materials', 'course information', 'how to use this course',
]

_STRONG_TEACHING_MARKERS = [
    # Vietnamese markers for actual lesson content.
    'khái niệm', 'định nghĩa', 'nguyên lý', 'quy trình', 'cấu trúc', 'thành phần', 'ví dụ',
    'cách hoạt động', 'phân loại', 'ưu điểm', 'nhược điểm', 'so sánh', 'áp dụng', 'triển khai',
    'mô hình', 'thuật toán', 'phương thức', 'giao thức', 'hàm', 'lớp', 'đối tượng', 'cơ sở dữ liệu',
    'api', 'http', 'request', 'response', 'database', 'authentication', 'authorization',
    # English markers.
    'definition', 'concept', 'principle', 'process', 'architecture', 'component', 'example',
    'how it works', 'classification', 'advantage', 'disadvantage', 'compare', 'implement',
    'algorithm', 'method', 'function', 'class', 'object', 'transaction', 'security',
]

_ADMIN_SOURCE_TYPES = {'course_info', 'overview', 'syllabus', 'navigation', 'toc', 'policy'}


def _normalize_text(text: str) -> str:
    return re.sub(r'\s+', ' ', (text or '').strip()).lower()


def _word_count(text: str) -> int:
    return len(re.findall(r'\w+', text or '', flags=re.UNICODE))


def content_signal(content: str, token_count: int = 0, *, title: str = '', source_type: str = '') -> ContentSignal:
    """Return whether a chunk is useful lesson content for question generation.

    Node Coverage should allocate questions from real teachable material, not
    navigation, course intro, grading policy, table of contents, or tiny title-only
    chunks. This is intentionally conservative: a long chunk that contains intro
    words but also has enough learning content is kept.
    """
    text = _normalize_text(f'{title}\n{content}')
    body = _normalize_text(content)
    words = _word_count(body)
    tokens = int(token_count or max(1, words * 1.3))
    source = _normalize_text(source_type)

    if not body:
        return ContentSignal(False, 0, 'empty_content')
    if source in _ADMIN_SOURCE_TYPES:
        return ContentSignal(False, 0, 'admin_source_type')
    if words < 35 or len(body) < 180:
        return ContentSignal(False, 0, 'too_short_for_learning_check')

    noise_hits = sum(1 for phrase in _NOISE_PHRASES if phrase in text)
    marker_hits = sum(1 for marker in _STRONG_TEACHING_MARKERS if marker in text)
    sentence_count = len(re.findall(r'[.!?。！？]|\n[-*•]|\n\d+[.)]', content or ''))

    # Short intro/admin chunks are the most common source of bad questions.
    if noise_hits and tokens < 220 and marker_hits == 0:
        return ContentSignal(False, 0, 'intro_or_admin_chunk')
    if noise_hits >= 2 and tokens < 350 and marker_hits <= 1:
        return ContentSignal(False, 0, 'mostly_intro_or_course_admin')

    # Keep actual lesson text. A transcript/file/html chunk can be useful even
    # without explicit markers if it has enough words and sentence structure.
    if marker_hits >= 1 or sentence_count >= 2 or words >= 120:
        # Penalize but do not fully remove long chunks that include an intro line.
        penalty = 0.7 if noise_hits and marker_hits else 1.0
        return ContentSignal(True, max(1, int(tokens * penalty)), 'teachable_content')

    return ContentSignal(False, 0, 'low_teaching_signal')


class NodeCoverageAllocator:
    """Allocate question quota across selected Open edX course nodes.

    v25.9.10: allocation is now weighted by *effective teachable tokens*, not by
    simple node count. Each meaningful selected node still receives coverage when
    the requested question count is large enough, but extra questions go to nodes
    that contain more real lesson content.
    """

    def allocate(self, nodes: list[dict], total_questions: int) -> list[NodeAllocation]:
        if total_questions <= 0:
            return []

        valid_nodes: list[dict] = []
        for node in nodes:
            effective_tokens = int(node.get('effective_token_count') or node.get('teachable_token_count') or 0)
            teachable_chunks = int(node.get('teachable_chunk_count') or 0)
            raw_tokens = int(node.get('token_count') or 0)
            raw_chunks = int(node.get('chunk_count') or 0)

            # Backward-compatible fallback: if callers did not pass teachable
            # metrics yet, use the old token/chunk fields rather than dropping all nodes.
            # If the caller explicitly passed teachable/effective metrics as 0,
            # it means the node only had intro/admin/non-learning chunks and must
            # not receive quota.
            has_teachable_metrics = any(key in node for key in ['effective_token_count', 'teachable_token_count', 'teachable_chunk_count'])
            if effective_tokens <= 0 and teachable_chunks <= 0 and not has_teachable_metrics:
                effective_tokens = raw_tokens
                teachable_chunks = raw_chunks
            if effective_tokens <= 0 or teachable_chunks <= 0:
                continue

            enriched = dict(node)
            enriched['effective_token_count'] = effective_tokens
            enriched['teachable_chunk_count'] = teachable_chunks
            valid_nodes.append(enriched)

        if not valid_nodes:
            return [NodeAllocation(
                node_id='course',
                title='Toàn bộ nội dung học hợp lệ',
                block_type='course',
                question_quota=total_questions,
                chunk_count=0,
                token_count=0,
                effective_token_count=0,
                teachable_chunk_count=0,
                skipped_chunk_count=0,
                allocation_weight=1.0,
            )]

        ordered = sorted(
            valid_nodes,
            key=lambda item: (
                int(item.get('effective_token_count') or 0),
                int(item.get('teachable_chunk_count') or 0),
                str(item.get('node_id') or ''),
            ),
            reverse=True,
        )

        # If there are more selected nodes than requested questions, choose the
        # most content-rich nodes. This avoids wasting questions on tiny intro nodes.
        if total_questions < len(ordered):
            chosen = ordered[:total_questions]
            total_weight = sum(max(1, int(item.get('effective_token_count') or 0)) for item in chosen)
            return [self._to_allocation(item, 1, total_weight) for item in chosen]

        # Coverage floor: every meaningful selected node gets at least one
        # question, then remaining questions are distributed by teachable tokens.
        quotas = {str(item.get('node_id')): 1 for item in ordered}
        remaining = total_questions - len(ordered)
        total_weight = sum(max(1, int(item.get('effective_token_count') or 0)) for item in ordered)

        remainders: list[tuple[float, int, str]] = []
        assigned_extra = 0
        for item in ordered:
            node_id = str(item.get('node_id'))
            weight = max(1, int(item.get('effective_token_count') or 0))
            raw_extra = remaining * weight / total_weight if total_weight else 0
            floor_extra = int(raw_extra)
            quotas[node_id] += floor_extra
            assigned_extra += floor_extra
            remainders.append((raw_extra - floor_extra, weight, node_id))

        missing = remaining - assigned_extra
        for _remainder, _weight, node_id in sorted(remainders, reverse=True)[:missing]:
            quotas[node_id] += 1

        allocations = [self._to_allocation(item, quotas[str(item.get('node_id'))], total_weight) for item in ordered]
        return [row for row in allocations if row.question_quota > 0]

    def _to_allocation(self, node: dict, quota: int, total_weight: int) -> NodeAllocation:
        effective_tokens = int(node.get('effective_token_count') or 0)
        return NodeAllocation(
            node_id=str(node.get('node_id')),
            title=str(node.get('title') or node.get('node_id')),
            block_type=str(node.get('block_type') or 'unknown'),
            question_quota=int(quota or 0),
            chunk_count=int(node.get('chunk_count') or 0),
            token_count=int(node.get('token_count') or 0),
            effective_token_count=effective_tokens,
            teachable_chunk_count=int(node.get('teachable_chunk_count') or 0),
            skipped_chunk_count=int(node.get('skipped_chunk_count') or 0),
            allocation_weight=round(effective_tokens / total_weight, 4) if total_weight else 0.0,
        )


def create_batches(total_questions: int, batch_size: int = 50) -> list[int]:
    batches: list[int] = []
    remaining = max(0, total_questions)
    while remaining:
        current = min(batch_size, remaining)
        batches.append(current)
        remaining -= current
    return batches
