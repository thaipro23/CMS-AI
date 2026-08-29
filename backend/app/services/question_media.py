from __future__ import annotations

import base64
import hashlib
import io
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.models.question import Question, QuestionMedia
from app.services.object_storage import ObjectStorage, StorageError, get_object_storage

ALLOWED_IMAGE_FORMATS = {
    'PNG': ('image/png', '.png'),
    'JPEG': ('image/jpeg', '.jpg'),
    'WEBP': ('image/webp', '.webp'),
}
MAX_QUESTION_IMAGE_BYTES = 4 * 1024 * 1024
MAX_QUESTION_IMAGES = 4
MAX_QUESTION_MEDIA_PUBLISH_BYTES = 16 * 1024 * 1024
MAX_IMAGE_PIXELS = 36_000_000


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _safe_file_stem(value: str) -> str:
    stem = re.sub(r'[^a-zA-Z0-9_.-]+', '-', Path(value or 'image').stem).strip('.-')
    return (stem or 'image')[:80]


@dataclass(frozen=True)
class ValidatedImage:
    raw: bytes
    mime_type: str
    extension: str
    width: int
    height: int
    sha256: str


def validate_question_image(raw: bytes, *, declared_content_type: str = '') -> ValidatedImage:
    data = bytes(raw or b'')
    if not data:
        raise ValueError('Ảnh không được để trống.')
    if len(data) > MAX_QUESTION_IMAGE_BYTES:
        raise ValueError('Ảnh câu hỏi tối đa 4 MB.')
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            fmt = str(image.format or '').upper()
            width, height = int(image.width), int(image.height)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError('File tải lên không phải ảnh hợp lệ.') from exc
    if fmt not in ALLOWED_IMAGE_FORMATS:
        raise ValueError('Chỉ hỗ trợ ảnh PNG, JPEG hoặc WebP. SVG không được phép.')
    if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
        raise ValueError('Kích thước ảnh không hợp lệ hoặc quá lớn.')
    mime_type, extension = ALLOWED_IMAGE_FORMATS[fmt]
    declared = str(declared_content_type or '').split(';', 1)[0].strip().lower()
    if declared and declared not in {'application/octet-stream', mime_type}:
        raise ValueError('Content-Type của file không khớp nội dung ảnh thực tế.')
    return ValidatedImage(
        raw=data,
        mime_type=mime_type,
        extension=extension,
        width=width,
        height=height,
        sha256=hashlib.sha256(data).hexdigest(),
    )


class QuestionMediaService:
    def __init__(self, db: Session, *, storage: ObjectStorage | None = None):
        self.db = db
        self.storage = storage or get_object_storage()

    def _require_question(self, bank_version_id: str, question_id: str) -> Question:
        question = self.db.get(Question, question_id)
        if not question or str(question.bank_version_id or '') != str(bank_version_id):
            raise ValueError('Không tìm thấy câu hỏi trong Bank Version đang chọn.')
        if str(question.status or '').lower() == 'published':
            raise ValueError('Không thể thay đổi media của câu hỏi đã published.')
        return question

    def list_media(self, bank_version_id: str, question_id: str) -> list[QuestionMedia]:
        self._require_question(bank_version_id, question_id)
        return (
            self.db.query(QuestionMedia)
            .filter(QuestionMedia.question_id == question_id, QuestionMedia.bank_version_id == bank_version_id)
            .order_by(QuestionMedia.sort_order.asc(), QuestionMedia.created_at.asc(), QuestionMedia.id.asc())
            .all()
        )

    def add_image(
        self,
        *,
        bank_version_id: str,
        question_id: str,
        filename: str,
        raw: bytes,
        content_type: str,
        alt_text: str,
        actor: str | None,
    ) -> QuestionMedia:
        question = self._require_question(bank_version_id, question_id)
        alt = str(alt_text or '').strip()
        if not alt:
            raise ValueError('Alt text là bắt buộc cho ảnh câu hỏi.')
        if len(alt) > 500:
            raise ValueError('Alt text tối đa 500 ký tự.')
        current = self.db.query(QuestionMedia).filter(QuestionMedia.question_id == question_id).all()
        if len(current) >= MAX_QUESTION_IMAGES:
            raise ValueError(f'Mỗi câu hỏi tối đa {MAX_QUESTION_IMAGES} ảnh.')
        validated = validate_question_image(raw, declared_content_type=content_type)
        existing = next((item for item in current if item.sha256 == validated.sha256), None)
        if existing:
            existing.alt_text = alt
            existing.updated_at = _utcnow_naive()
            self.db.add(existing)
            self.db.commit()
            self.db.refresh(existing)
            return existing

        media_id = str(uuid.uuid4())
        safe_name = _safe_file_stem(filename)
        key = f'question-media/{bank_version_id}/{question_id}/{media_id}-{safe_name}-{validated.sha256[:12]}{validated.extension}'
        reference = self.storage.put_bytes(key, validated.raw, content_type=validated.mime_type)
        media = QuestionMedia(
            id=media_id,
            question_id=question_id,
            bank_version_id=bank_version_id,
            media_role='prompt_image',
            storage_reference=reference,
            file_name=f'{safe_name}{validated.extension}',
            mime_type=validated.mime_type,
            size_bytes=len(validated.raw),
            sha256=validated.sha256,
            width=validated.width,
            height=validated.height,
            alt_text=alt,
            sort_order=max([int(item.sort_order or 0) for item in current], default=-1) + 1,
            created_by=actor,
        )
        self.db.add(media)
        question.updated_at = _utcnow_naive()
        self.db.add(question)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            try:
                self.storage.delete(reference, missing_ok=True)
            except StorageError:
                pass
            raise
        self.db.refresh(media)
        return media

    def update_alt(
        self,
        *,
        bank_version_id: str,
        question_id: str,
        media_id: str,
        alt_text: str,
        sort_order: int | None = None,
    ) -> QuestionMedia:
        self._require_question(bank_version_id, question_id)
        media = (
            self.db.query(QuestionMedia)
            .filter(
                QuestionMedia.id == media_id,
                QuestionMedia.question_id == question_id,
                QuestionMedia.bank_version_id == bank_version_id,
            )
            .first()
        )
        if not media:
            raise ValueError('Không tìm thấy media của câu hỏi.')
        alt = str(alt_text or '').strip()
        if not alt:
            raise ValueError('Alt text là bắt buộc.')
        media.alt_text = alt[:500]
        if sort_order is not None:
            media.sort_order = max(0, int(sort_order))
        media.updated_at = _utcnow_naive()
        self.db.add(media)
        self.db.commit()
        self.db.refresh(media)
        return media

    def delete(self, *, bank_version_id: str, question_id: str, media_id: str) -> dict:
        self._require_question(bank_version_id, question_id)
        media = (
            self.db.query(QuestionMedia)
            .filter(
                QuestionMedia.id == media_id,
                QuestionMedia.question_id == question_id,
                QuestionMedia.bank_version_id == bank_version_id,
            )
            .first()
        )
        if not media:
            raise ValueError('Không tìm thấy media của câu hỏi.')
        reference = media.storage_reference
        self.db.delete(media)
        self.db.commit()
        file_deleted = False
        try:
            file_deleted = bool(self.storage.delete(reference, missing_ok=True))
        except StorageError:
            # DB deletion is authoritative. Orphan cleanup can be retried operationally.
            file_deleted = False
        return {
            'ok': True,
            'media_id': media_id,
            'question_id': question_id,
            'file_deleted': file_deleted,
            'message': 'Đã xóa ảnh khỏi câu hỏi.',
        }


def build_openedx_question_assets(
    db: Session,
    question: Question,
    *,
    storage: ObjectStorage | None = None,
) -> tuple[list[QuestionMedia], list[dict]]:
    rows = (
        db.query(QuestionMedia)
        .filter(QuestionMedia.question_id == question.id)
        .order_by(QuestionMedia.sort_order.asc(), QuestionMedia.created_at.asc(), QuestionMedia.id.asc())
        .all()
    )
    if not rows:
        return [], []
    object_storage = storage or get_object_storage()
    total = 0
    assets: list[dict] = []
    for row in rows:
        raw = object_storage.read_bytes(row.storage_reference)
        if hashlib.sha256(raw).hexdigest() != str(row.sha256 or ''):
            raise ValueError(f'Ảnh {row.id} không còn khớp checksum đã lưu; dừng publish để tránh dùng media sai.')
        total += len(raw)
        if total > MAX_QUESTION_MEDIA_PUBLISH_BYTES:
            raise ValueError('Tổng dung lượng ảnh của một câu vượt giới hạn publish 16 MB.')
        extension = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp'}.get(row.mime_type)
        if not extension:
            raise ValueError(f'MIME ảnh {row.mime_type!r} không được hỗ trợ khi publish.')
        assets.append({
            'placeholder': f'__ACMS_MEDIA_{row.id}__',
            'file_path': f'acms/{question.id}/{row.sha256[:20]}{extension}',
            'content_type': row.mime_type,
            'content_b64': base64.b64encode(raw).decode('ascii'),
            'sha256': row.sha256,
            'size_bytes': len(raw),
        })
    return rows, assets
