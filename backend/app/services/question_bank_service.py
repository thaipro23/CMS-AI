from __future__ import annotations

import re
import uuid
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.question import Question
from app.models.question_bank import (
    BankReleaseQuestion,
    Department,
    EdxCourseChapterMapping,
    EdxCourseMapping,
    LearningMaterialVersion,
    QuestionBankRelease,
    QuestionBankVersion,
    QuizBlueprint,
    Subject,
    SubjectChapter,
)


def slugify(value: str, fallback: str = 'item') -> str:
    text = (value or '').strip().lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text or fallback


class VersionedQuestionBankService:
    """Question Bank-first service.

    v25.9.15 keeps this service deterministic: no LLM call, no Open edX write.
    It creates the domain model and immutable Release record that later publish
    code maps 1:1 to a Content Library.
    """

    def __init__(self, db: Session):
        self.db = db

    def summary(self) -> dict:
        return {
            'departments': self.db.query(Department).count(),
            'subjects': self.db.query(Subject).count(),
            'chapters': self.db.query(SubjectChapter).count(),
            'bank_versions': self.db.query(QuestionBankVersion).count(),
            'releases': self.db.query(QuestionBankRelease).count(),
            'published_releases': self.db.query(QuestionBankRelease).filter(QuestionBankRelease.status == 'published').count(),
            'course_mappings': self.db.query(EdxCourseMapping).count(),
            'quiz_blueprints': self.db.query(QuizBlueprint).count(),
        }

    def create_department(self, *, code: str, name: str, description: str = '') -> Department:
        item = Department(id=str(uuid.uuid4()), code=code.strip().upper(), name=name.strip(), description=description or '')
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def create_subject(self, *, department_id: str, code: str, name: str, description: str = '') -> Subject:
        item = Subject(id=str(uuid.uuid4()), department_id=department_id, code=code.strip().upper(), name=name.strip(), description=description or '')
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def create_chapter(self, *, subject_id: str, chapter_no: int, title: str, description: str = '', sort_order: int | None = None) -> SubjectChapter:
        item = SubjectChapter(id=str(uuid.uuid4()), subject_id=subject_id, chapter_no=chapter_no, title=title.strip(), description=description or '', sort_order=sort_order or chapter_no)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def next_bank_version_no(self, subject_id: str, chapter_id: str) -> int:
        value = self.db.query(func.max(QuestionBankVersion.version_no)).filter(
            QuestionBankVersion.subject_id == subject_id,
            QuestionBankVersion.chapter_id == chapter_id,
        ).scalar()
        return int(value or 0) + 1

    def create_bank_version(self, *, subject_id: str, chapter_id: str, version_code: str, title: str = '', change_note: str = '', based_on_version_id: str | None = None, actor: str | None = None) -> QuestionBankVersion:
        item = QuestionBankVersion(
            id=str(uuid.uuid4()),
            subject_id=subject_id,
            chapter_id=chapter_id,
            version_no=self.next_bank_version_no(subject_id, chapter_id),
            version_code=version_code.strip() or 'v1.0',
            title=title.strip(),
            change_note=change_note or '',
            based_on_version_id=based_on_version_id,
            created_by=actor,
            metadata_json={'architecture': 'question_bank_first', 'release_policy': 'one_release_one_openedx_library'},
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def create_material_version(self, *, subject_id: str, chapter_id: str, bank_version_id: str, title: str = '', file_name: str = '', file_type: str = 'unknown', storage_path: str = '', content_hash: str | None = None, version_no: int = 1, change_type: str = 'initial', actor: str | None = None) -> LearningMaterialVersion:
        item = LearningMaterialVersion(
            id=str(uuid.uuid4()),
            subject_id=subject_id,
            chapter_id=chapter_id,
            bank_version_id=bank_version_id,
            title=title,
            file_name=file_name,
            file_type=file_type,
            storage_path=storage_path,
            content_hash=content_hash,
            version_no=version_no,
            change_type=change_type,
            uploaded_by=actor,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def release_library_key(self, *, subject: Subject, chapter: SubjectChapter, version: QuestionBankVersion) -> str:
        subject_slug = slugify(subject.code or subject.name, 'subject')
        chapter_slug = f'bai-{chapter.chapter_no}' if chapter.chapter_no else slugify(chapter.title, 'chapter')
        version_slug = slugify(version.version_code.replace('.', '-'), 'v1')
        return f'lib:FPT:{subject_slug}-{chapter_slug}-{version_slug}'

    def create_release(self, *, bank_version_id: str, release_code: str | None = None, title: str = '', include_approved_questions: bool = True, actor: str | None = None) -> QuestionBankRelease:
        version = self.db.get(QuestionBankVersion, bank_version_id)
        if not version:
            raise ValueError('Không tìm thấy Bank Version')
        subject = self.db.get(Subject, version.subject_id)
        chapter = self.db.get(SubjectChapter, version.chapter_id)
        if not subject or not chapter:
            raise ValueError('Bank Version thiếu Subject hoặc Chapter')
        code = release_code or f'{subject.code}-B{chapter.chapter_no}-{version.version_code}'
        library_key = self.release_library_key(subject=subject, chapter=chapter, version=version)
        base_query = self.db.query(Question).filter(
            Question.bank_version_id == version.id,
            Question.status.in_(['approved', 'published']),
        )
        questions = base_query.all() if include_approved_questions else []
        if not questions:
            # Release can be drafted before questions are generated, but it cannot
            # be marked published without questions. This is intentional for a
            # bank-first guided setup flow.
            status = 'draft'
        else:
            status = 'published'
        counts = {'easy': 0, 'medium': 0, 'hard': 0}
        families = set()
        for question in questions:
            diff = (question.difficulty or 'easy').lower()
            counts[diff if diff in counts else 'easy'] += 1
            if question.question_family_id:
                families.add(question.question_family_id)
        release = QuestionBankRelease(
            id=str(uuid.uuid4()),
            bank_version_id=version.id,
            subject_id=version.subject_id,
            chapter_id=version.chapter_id,
            release_code=code,
            title=title or f'{subject.code} - Bài {chapter.chapter_no} - {version.version_code}',
            status=status,
            approved_question_count=len(questions),
            easy_count=counts['easy'],
            medium_count=counts['medium'],
            hard_count=counts['hard'],
            family_count=len(families),
            openedx_library_key=library_key,
            published_at=datetime.utcnow() if status == 'published' else None,
            published_by=actor if status == 'published' else None,
            metadata_json={'one_bank_release_one_openedx_library': True, 'shared_across_courses': True},
        )
        self.db.add(release)
        self.db.flush()
        for question in questions:
            self.db.add(BankReleaseQuestion(
                id=str(uuid.uuid4()),
                bank_release_id=release.id,
                question_id=question.id,
                question_family_id=question.question_family_id,
                difficulty=question.difficulty,
                openedx_library_problem_id=question.openedx_library_problem_id,
            ))
            question.bank_release_id = release.id
        if status == 'published':
            version.status = 'published'
            version.published_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(release)
        return release

    def create_course_mapping(self, *, openedx_course_id: str, subject_id: str, department_id: str | None = None, term: str | None = None, actor: str | None = None) -> EdxCourseMapping:
        item = EdxCourseMapping(id=str(uuid.uuid4()), openedx_course_id=openedx_course_id.strip(), subject_id=subject_id, department_id=department_id, term=term, created_by=actor)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def create_course_chapter_mapping(self, *, course_mapping_id: str, subject_chapter_id: str, bank_release_id: str | None = None, openedx_parent_node_id: str | None = None, enabled: bool = True) -> EdxCourseChapterMapping:
        item = EdxCourseChapterMapping(id=str(uuid.uuid4()), course_mapping_id=course_mapping_id, subject_chapter_id=subject_chapter_id, bank_release_id=bank_release_id, openedx_parent_node_id=openedx_parent_node_id, enabled=enabled)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def create_quiz_blueprint(self, *, subject_id: str, chapter_id: str, title: str, total_questions: int, difficulty_easy: int, difficulty_medium: int, difficulty_hard: int, max_families_per_bank: int = 2, pick_count_per_slot: int = 1) -> QuizBlueprint:
        total_pct = difficulty_easy + difficulty_medium + difficulty_hard
        if total_pct != 100:
            raise ValueError('Tỷ lệ EASY/MEDIUM/HARD phải bằng 100')
        item = QuizBlueprint(id=str(uuid.uuid4()), subject_id=subject_id, chapter_id=chapter_id, title=title, total_questions=total_questions, difficulty_easy=difficulty_easy, difficulty_medium=difficulty_medium, difficulty_hard=difficulty_hard, max_families_per_bank=max_families_per_bank, pick_count_per_slot=pick_count_per_slot)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item
