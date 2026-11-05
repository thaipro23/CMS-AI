"""Operator repair for the eight existing WEB3023_SU26 Libraries; no course reset.

Run inside the deployed AI worker image, from a file or Python stdin. Without
--execute this only prints the validated plan. An extra Final test chapter is
outside scope. Direct task.run retains durable jobs/audit without Redis enqueue.
"""
import argparse
import json

from sqlalchemy import text

from app.db.session import SessionLocal, engine
from app.models.question_bank import (
    BankOperationJob, QuestionBankRelease, QuestionBankVersion,
    Subject, SubjectChapter, SubjectOffering,
)
from app.services.bank_operation_jobs import BankOperationJobService
from app.services.question_bank_service import VersionedQuestionBankService

OFFERING_ID = 'f5604c81-3f72-4fa5-8fc0-5dcefd5a26e0'
LOCK_KEY = 20261105083023


def validate_scope(offering, subject, chapters):
    if not offering or not subject or subject.code.upper() != 'WEB3023':
        raise ValueError('Offering không thuộc WEB3023; không thay đổi dữ liệu.')
    if offering.id != OFFERING_ID or subject.id != offering.subject_id:
        raise ValueError('Sai phiên bản môn học; không thay đổi dữ liệu.')
    # The offering also contains chapter 9 "Final test". The authorized repair
    # covers only Bài 1–8; extra chapters must not change that target scope.
    chapters = [chapter for chapter in chapters if 1 <= chapter.chapter_no <= 8]
    if len(chapters) != 8 or sorted(c.chapter_no for c in chapters) != list(range(1, 9)):
        raise ValueError('Cần đúng 8 Bài, số thứ tự 1–8; không thay đổi dữ liệu.')
    if any(c.subject_offering_id != OFFERING_ID or c.subject_id != subject.id for c in chapters):
        raise ValueError('Bài học khác phiên bản/môn; không thay đổi dữ liệu.')
    return chapters


def require_no_active_job(db, release_id):
    active = db.query(BankOperationJob).filter(
        BankOperationJob.release_id == release_id,
        BankOperationJob.operation_type == 'release_publish',
        BankOperationJob.status.in_(['queued', 'running']),
    ).first()
    if active:
        raise ValueError(f'Release {release_id} đang có job {active.id}: {active.status}; dừng.')


def build_plan(db):
    offering = db.get(SubjectOffering, OFFERING_ID)
    subject = db.get(Subject, offering.subject_id) if offering else None
    chapters = db.query(SubjectChapter).filter(
        SubjectChapter.subject_offering_id == OFFERING_ID,
        SubjectChapter.status != 'archived',
    ).order_by(SubjectChapter.chapter_no).all()
    chapters = validate_scope(offering, subject, chapters)
    service = VersionedQuestionBankService(db)
    workflow = service._release_publish_workflow()
    plan = []
    for chapter in chapters:
        release = db.query(QuestionBankRelease).filter(
            QuestionBankRelease.chapter_id == chapter.id,
            QuestionBankRelease.published_at.isnot(None),
            QuestionBankRelease.status.in_(['published', 'publish_failed']),
        ).order_by(QuestionBankRelease.created_at.desc(), QuestionBankRelease.id.desc()).first()
        if not release or release.subject_id != subject.id or not release.openedx_library_key:
            raise ValueError(f'Bài {chapter.chapter_no}: thiếu Release/Library đã publish; dừng.')
        version = db.get(QuestionBankVersion, release.bank_version_id)
        if not version or version.subject_offering_id != OFFERING_ID:
            raise ValueError(f'Bài {chapter.chapter_no}: Bank Version khác phiên bản môn; dừng.')
        expected = service.release_library_key(subject=subject, chapter=chapter, version=version)
        if (not service._library_key_same(release.openedx_library_key, expected)
                or service._release_library_key_needs_term_upgrade(
                    library_key=release.openedx_library_key, subject=subject, version=version)):
            raise ValueError(f'Bài {chapter.chapter_no}: Library key sẽ đổi; dừng để giữ mapping course.')
        items, _ = workflow._load_frozen_release_snapshot(release)
        if not items or any(not item.openedx_library_problem_id for item in items):
            raise ValueError(f'Bài {chapter.chapter_no}: snapshot thiếu component ID; dừng.')
        identity = {'library_key': release.openedx_library_key, 'components': {
            str(item.question_id): str(item.openedx_library_problem_id) for item in items}}
        workflow._validate_repair_identity(release, items, identity, expected)
        require_no_active_job(db, release.id)
        plan.append({'chapter': chapter.chapter_no, 'release_id': release.id,
                     'bank_version_id': version.id, 'release_code': release.release_code,
                     'library_key': release.openedx_library_key, 'questions': len(items),
                     'repair_expectations': identity})
    return plan


def run(execute=False):
    if engine.dialect.name != 'postgresql':
        raise ValueError('Lệnh vận hành cần PostgreSQL production.')
    with engine.connect() as lock:
        if not lock.execute(text('SELECT pg_try_advisory_lock(:key)'), {'key': LOCK_KEY}).scalar():
            raise ValueError('Một phiên sửa WEB3023 khác đang chạy; dừng.')
        lock.commit()
        try:
            with SessionLocal() as db:
                plan = build_plan(db)
                summary = [{k: v for k, v in row.items() if k != 'repair_expectations'} for row in plan]
                print(json.dumps({'execute': execute, 'offering_id': OFFERING_ID, 'plan': summary},
                                 ensure_ascii=False, indent=2), flush=True)
            if not execute:
                print('DRY_RUN_OK: chưa tạo job hoặc gọi CMS. Thêm --execute để chạy.', flush=True)
                return
            from app.worker import bank_release_publish_task

            for row in plan:
                with SessionLocal() as db:
                    # Same Release lock as the API; recheck before each real job.
                    db.query(QuestionBankRelease).filter(
                        QuestionBankRelease.id == row['release_id'],
                    ).with_for_update().one()
                    require_no_active_job(db, row['release_id'])
                    current = next(p for p in build_plan(db) if p['chapter'] == row['chapter'])
                    if current != row:
                        raise ValueError('Kế hoạch đã thay đổi trong khi chạy; dừng trước job tiếp theo.')
                    job = BankOperationJobService(db).create_job(
                        operation_type='release_publish', target_type='bank_release',
                        target_id=row['release_id'], release_id=row['release_id'],
                        requested_by='k8s-operator:web3023-html-repair',
                        bank_version_id=row['bank_version_id'],
                        request_json={'release_id': row['release_id'], 'force_reimport': True,
                                      'repair_expectations': row['repair_expectations'],
                                      'operator_execution': 'k8s-web3023-html-repair-direct'},
                        progress_total=100, progress_label='K8s: chuẩn bị tái xuất OLX WEB3023',
                    )
                    job_id = job.id
                print(f"START Bài {row['chapter']}/8 job={job_id}", flush=True)
                # Synchronous task body, no apply_async/broker dependency.
                bank_release_publish_task.run(job_id)
                with SessionLocal() as db:
                    job = db.get(BankOperationJob, job_id)
                    if not job or job.status != 'completed' or not (job.result_json or {}).get('ok'):
                        raise RuntimeError(f'Job {job_id} chưa hoàn tất; dừng, không đánh dấu thành công.')
                    print(json.dumps({'chapter': row['chapter'], 'job_id': job_id,
                                      'result': job.result_json}, ensure_ascii=False), flush=True)
            print('DONE 8/8 LIBRARIES. Course copy vẫn cần cập nhật từ Library trong Studio.', flush=True)
        finally:
            lock.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': LOCK_KEY})
            lock.commit()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    run(parser.parse_args().execute)
