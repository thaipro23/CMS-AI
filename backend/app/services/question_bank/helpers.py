from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.openedx_ids import normalize_openedx_course_id
from app.models.question import Question

def slugify(value: str, fallback: str = 'item') -> str:
    text = (value or '').strip().lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text or fallback


def normalize_text(value: str | None) -> str:
    return re.sub(r'\s+', ' ', (value or '').strip().lower())


def normalize_code(value: str | None) -> str:
    return re.sub(r'[^a-z0-9]', '', (value or '').lower())




def normalize_title_match(value: str | None) -> str:
    text = unicodedata.normalize('NFD', value or '')
    text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_chapter_number(value: str | None) -> str | None:
    text = normalize_title_match(value)
    match = re.search(r'\b(?:bai|chapter|section)\s*([0-9]+(?:\.[0-9]+)*)\b', text)
    if match:
        return match.group(1)
    match = re.search(r'^([0-9]+(?:\.[0-9]+)*)\b', text)
    return match.group(1) if match else None

def parse_openedx_course_id(course_id: str) -> dict[str, str | None]:
    normalized = normalize_openedx_course_id(course_id)
    if not normalized:
        return {'ok': False, 'org': None, 'course_code': None, 'run': None, 'normalized_course_id': None}
    match = re.match(r'^course-v1:([^+]+)\+([^+]+)\+([^+/]+)$', normalized)
    if not match:
        return {'ok': False, 'org': None, 'course_code': None, 'run': None, 'normalized_course_id': None}
    return {
        'ok': True,
        'org': match.group(1),
        'course_code': match.group(2),
        'run': match.group(3),
        'normalized_course_id': normalized,
    }


TERM_SEASON_LABELS = {
    'SP': {'en': 'Spring', 'vi': 'Xuân'},
    'SU': {'en': 'Summer', 'vi': 'Hè'},
    'FA': {'en': 'Fall', 'vi': 'Fall/Đông'},
}

def normalize_academic_term_code(*, term: str | None = None, season: str | None = None, year: int | str | None = None, code: str | None = None) -> dict[str, str | int | None]:
    """Normalize FPT-style academic term codes.

    Term is the version layer of a subject version, not an Open edX course run.
    Supported seasons: SP (Spring/Xuân), SU (Summer/Hè), FA (Fall/Đông).
    Examples: SP25, SU26, FA27. The numeric suffix is the 2-digit year.
    """
    raw = (term or code or '').strip().upper().replace('_', '').replace('-', '').replace(' ', '')
    parsed_season = None
    parsed_year = None
    match = re.match(r'^(SP|SU|FA)(\d{2}|\d{4})$', raw)
    if match:
        parsed_season = match.group(1)
        parsed_year = int(match.group(2))
    if season:
        s = season.strip().upper()
        aliases = {'SPRING': 'SP', 'XUAN': 'SP', 'XUÂN': 'SP', 'SUMMER': 'SU', 'HE': 'SU', 'HÈ': 'SU', 'FALL': 'FA', 'AUTUMN': 'FA', 'THU': 'FA', 'DONG': 'FA', 'ĐÔNG': 'FA'}
        parsed_season = aliases.get(s, s[:2])
    if year is not None and str(year).strip():
        y = int(str(year).strip())
        parsed_year = y
    if parsed_season not in TERM_SEASON_LABELS:
        raise ValueError('Kỳ chỉ hỗ trợ SP/Spring, SU/Summer, FA/Fall. Ví dụ: SP25, SU26, FA27.')
    if parsed_year is None:
        raise ValueError('Thiếu năm của kỳ. Ví dụ: SP25 nghĩa là Spring 2025.')
    year2 = parsed_year % 100
    year_full = 2000 + year2 if parsed_year < 100 else parsed_year
    term_code = f'{parsed_season}{year2:02d}'
    labels = TERM_SEASON_LABELS[parsed_season]
    return {
        'term_code': term_code,
        'season': parsed_season,
        'season_name': labels['en'],
        'season_name_vi': labels['vi'],
        'year': year_full,
        'year_short': f'{year2:02d}',
        'display_name': f"{labels['en']} {year_full}",
        'display_name_vi': f"{labels['vi']} {year_full}",
    }


def extract_block_course_tuple(block_id: str | None) -> dict[str, str | None]:
    text = (block_id or '').strip()
    match = re.match(r'^block-v1:([^+]+)\+([^+]+)\+([^+]+)\+type@([^+]+)\+block@(.+)$', text)
    if not match:
        return {'ok': False, 'org': None, 'course_code': None, 'run': None, 'block_type': None}
    return {'ok': True, 'org': match.group(1), 'course_code': match.group(2), 'run': match.group(3), 'block_type': match.group(4)}


def title_similarity(a: str | None, b: str | None) -> float:
    a_norm = normalize_text(a)
    b_norm = normalize_text(b)
    if not a_norm or not b_norm:
        return 0.0
    return SequenceMatcher(None, a_norm, b_norm).ratio()



BANK_UPLOAD_ALLOWED_EXTENSIONS = {
    'pdf', 'pptx', 'ppt', 'docx', 'xlsx', 'xlsm', 'csv', 'tsv',
    'txt', 'md', 'markdown', 'html', 'htm', 'json', 'xml', 'vtt', 'srt',
}
BANK_UPLOAD_LEGACY_OFFICE_EXTENSIONS = {'doc', 'xls'}
BANK_UPLOAD_MAX_BYTES = 50 * 1024 * 1024


def safe_upload_filename(filename: str) -> str:
    name = (filename or 'uploaded-file').replace('\\', '/').rsplit('/', 1)[-1].strip()
    name = re.sub(r'[^0-9A-Za-zÀ-ỹ._ -]+', '_', name)
    return name[:180] or 'uploaded-file'


def upload_extension(filename: str) -> str:
    name = filename.rsplit('.', 1)
    return name[1].lower() if len(name) == 2 else ''


def chunk_policy_for_material_source(source_type: str) -> tuple[int, int]:
    source = (source_type or '').lower()
    if source in {'csv', 'tsv', 'xlsx', 'xlsm'}:
        return 1100, 80
    if source in {'pdf', 'pptx', 'ppt', 'docx'}:
        return 1000, 120
    if source in {'srt', 'vtt'}:
        return 900, 100
    return 1000, 100


def bank_material_storage_dir(bank_version_id: str) -> Path:
    root = Path(settings.local_storage_path or '/app/.runtime')
    return root / 'question-bank' / str(bank_version_id)


def _check(code: str, status: str, message: str, detail: dict | None = None, blocking: bool | None = None) -> dict[str, Any]:
    if blocking is None:
        blocking = status == 'fail'
    return {'code': code, 'status': status, 'message': message, 'blocking': bool(blocking), 'detail': detail or {}}


def question_lineage_root(question: Question) -> str:
    return question.lineage_root_question_id or question.previous_question_id or question.id


def normalize_question_text_for_diff(value: str | None) -> str:
    return re.sub(r'[^a-z0-9à-ỹ]+', ' ', (value or '').lower()).strip()


def bank_text_similarity(a: str | None, b: str | None) -> float:
    a_norm = normalize_question_text_for_diff(a)
    b_norm = normalize_question_text_for_diff(b)
    if not a_norm or not b_norm:
        return 0.0
    if a_norm == b_norm:
        return 1.0
    # Avoid O(n^2) huge comparisons from full documents by capping the strings.
    return SequenceMatcher(None, a_norm[:12000], b_norm[:12000]).ratio()




AUTO_RETIRE_MIN_EVIDENCE_CHARS = 60
AUTO_RETIRE_STRONG_CHUNK_SIMILARITY = 0.82
AUTO_RETIRE_TOKEN_OVERLAP_THRESHOLD = 0.58
AUTO_RETIRE_MIN_TOKEN_COUNT = 8


def _evidence_tokens(value: str | None) -> set[str]:
    text = normalize_question_text_for_diff(value)
    if not text:
        return set()
    return {token for token in text.split() if len(token) >= 3}


def _token_overlap_ratio(evidence: str | None, material: str | None) -> float:
    evidence_tokens = _evidence_tokens(evidence)
    if len(evidence_tokens) < AUTO_RETIRE_MIN_TOKEN_COUNT:
        return 0.0
    material_tokens = _evidence_tokens(material)
    if not material_tokens:
        return 0.0
    return len(evidence_tokens & material_tokens) / max(len(evidence_tokens), 1)


def _bounded_similarity(a: str | None, b: str | None, *, max_chars: int = 2400) -> float:
    a_norm = normalize_question_text_for_diff(a)[:max_chars]
    b_norm = normalize_question_text_for_diff(b)[:max_chars]
    if not a_norm or not b_norm:
        return 0.0
    if a_norm == b_norm:
        return 1.0
    return SequenceMatcher(None, a_norm, b_norm).ratio()

def stable_concept_identity(question: Question) -> str:
    return slugify(question.concept_key or question.concept_title or question.topic or question.learning_objective or 'unknown-concept', 'concept')




def _ui_notice(status: str, message: str, title: str | None = None) -> dict:
    normalized = (status or 'info').strip().lower()
    if normalized == 'danger':
        normalized = 'error'
    if normalized not in {'success', 'error', 'warning', 'info'}:
        normalized = 'info'
    default_titles = {
        'success': 'Thành công',
        'error': 'Có lỗi',
        'warning': 'Cần kiểm tra',
        'info': 'Thông báo',
    }
    return {
        'ui_status': normalized,
        'ui_title': title or default_titles[normalized],
        'ui_message': message,
    }
