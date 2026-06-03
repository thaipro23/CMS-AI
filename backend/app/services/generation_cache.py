from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.generation_cache import GenerationCache
from app.services.prompt_builder import PROMPT_VERSION


def sha256_text(value: str, length: int = 64) -> str:
    return hashlib.sha256((value or '').encode('utf-8')).hexdigest()[:length]


def normalize_question_text(value: str) -> str:
    text = (value or '').strip().lower()
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\w\sÀ-ỹ]', '', text, flags=re.UNICODE)
    return text.strip()


def question_fingerprint(question_text: str, *, course_id: str, source_node_id: str | None, difficulty: str | None) -> str:
    normalized = normalize_question_text(question_text)
    scope = f'{course_id}|{source_node_id or "unknown-node"}|{difficulty or "unknown-difficulty"}|{normalized}'
    return sha256_text(scope, 64)


def build_prompt_cache_key(*, course_id: str, scope_title: str | None, content: str, chunk_ids: list[str] | None = None, node_id: str | None = None) -> str:
    """Stable key shared by EASY/MEDIUM/HARD calls for the same content prefix."""
    content_hash = sha256_text(content, 32)
    chunk_part = ','.join(sorted(chunk_ids or []))[:500]
    raw = f'course:{course_id}|node:{node_id or "batch"}|scope:{scope_title or ""}|chunks:{chunk_part}|content:{content_hash}|prompt:{PROMPT_VERSION}'
    return 'ai-openedx:' + sha256_text(raw, 48)


def build_generation_cache_key(*, prompt_cache_key: str, difficulty: str | None, question_count: int, model_name: str | None = None) -> str:
    raw = f'{prompt_cache_key}|difficulty:{difficulty or "mixed"}|count:{int(question_count or 0)}|model:{model_name or settings.openai_model}|prompt:{PROMPT_VERSION}'
    return sha256_text(raw, 64)


class GenerationCacheService:
    def __init__(self, db: Session):
        self.db = db

    def get_cached_questions(self, cache_key: str, min_count: int) -> list[dict] | None:
        row = self.db.query(GenerationCache).filter(GenerationCache.cache_key == cache_key).first()
        if not row or not isinstance(row.parsed_questions_json, list):
            return None
        questions = row.parsed_questions_json
        if len(questions) < int(min_count or 0):
            return None
        row.hit_count = int(row.hit_count or 0) + 1
        row.updated_at = datetime.utcnow()
        self.db.add(row)
        self.db.commit()
        return questions[: int(min_count or 0)]

    def save_success(
        self,
        *,
        cache_key: str,
        prompt_cache_key: str | None,
        course_id: str | None,
        source_node_id: str | None,
        chunk_hash: str | None,
        difficulty: str | None,
        question_count: int,
        model_name: str,
        raw_output_text: str | None,
        parsed_questions: list[dict],
        response_id: str | None,
        input_tokens: int,
        cached_input_tokens: int,
        output_tokens: int,
        parse_error: str | None = None,
    ) -> GenerationCache:
        row = self.db.query(GenerationCache).filter(GenerationCache.cache_key == cache_key).first()
        if not row:
            row = GenerationCache(cache_key=cache_key, created_at=datetime.utcnow())
        row.prompt_cache_key = prompt_cache_key
        row.course_id = course_id
        row.source_node_id = source_node_id
        row.chunk_hash = chunk_hash
        row.difficulty = difficulty
        row.question_count = int(question_count or len(parsed_questions) or 0)
        row.prompt_version = PROMPT_VERSION
        row.model_name = model_name
        row.raw_output_text = raw_output_text
        row.parsed_questions_json = parsed_questions
        row.question_hashes = [sha256_text(json.dumps(q, ensure_ascii=False, sort_keys=True), 32) for q in parsed_questions]
        row.response_id = response_id
        row.parse_error = parse_error
        row.input_tokens = int(input_tokens or 0)
        row.cached_input_tokens = int(cached_input_tokens or 0)
        row.output_tokens = int(output_tokens or 0)
        row.updated_at = datetime.utcnow()
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def save_parse_failure(
        self,
        *,
        cache_key: str,
        prompt_cache_key: str | None,
        course_id: str | None,
        source_node_id: str | None,
        chunk_hash: str | None,
        difficulty: str | None,
        question_count: int,
        model_name: str,
        raw_output_text: str | None,
        response_id: str | None,
        input_tokens: int,
        cached_input_tokens: int,
        output_tokens: int,
        parse_error: str,
    ) -> GenerationCache:
        return self.save_success(
            cache_key=cache_key,
            prompt_cache_key=prompt_cache_key,
            course_id=course_id,
            source_node_id=source_node_id,
            chunk_hash=chunk_hash,
            difficulty=difficulty,
            question_count=question_count,
            model_name=model_name,
            raw_output_text=raw_output_text,
            parsed_questions=[],
            response_id=response_id,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            parse_error=parse_error,
        )
