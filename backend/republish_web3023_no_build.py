"""One-off WEB3023 repair, executed from stdin in an existing AI worker pod."""
import asyncio
from contextlib import contextmanager
import json
import uuid
from xml.etree import ElementTree as ET

OFFERING_ID = 'f5604c81-3f72-4fa5-8fc0-5dcefd5a26e0'


@contextmanager
def protect_library_identity(service_class, workflow_class):
    owners = (service_class, workflow_class)
    originals = [owner._reset_release_openedx_state_for_key_change for owner in owners]
    def refuse_reset(*args, **kwargs):
        raise RuntimeError('Repair refused a Library identity reset')
    try:
        for owner in owners:
            owner._reset_release_openedx_state_for_key_change = refuse_reset
        yield
    finally:
        for owner, original in zip(owners, originals):
            owner._reset_release_openedx_state_for_key_change = original


def literal_olx(olx):
    root = ET.fromstring(olx)
    # Only display text at CAPA stringify boundaries. Grading attributes,
    # dropdown options, image nodes and existing escaped HTML children stay intact.
    for node in list(root.iter()):
        if node.tag in {'label', 'choice', 'choicehint', 'hint'} and node.text and any(c in node.text for c in '<>&'):
            span = ET.Element('span', {'style': 'white-space: pre-wrap'})
            span.text, node.text = node.text, None
            node.insert(0, span)
    return ET.tostring(root, encoding='unicode')


class ExistingLibraryRepairConnector:
    def __init__(self, native, library_key, components):
        self.native = native
        self.library_key = library_key
        self.components = components

    def __getattr__(self, name):
        return getattr(self.native, name)

    def check(self, library_key, problem_id=None):
        if library_key != self.library_key:
            raise RuntimeError('Repair refused a different Library key')
        if problem_id is not None and str(problem_id) not in self.components.values():
            raise RuntimeError('Repair refused an unknown existing component')

    async def ensure_problem_library(self, course_id, chapter_node_id, display_name, metadata=None):
        self.check((metadata or {}).get('library_key'))
        # All components were verified during preflight. Never create a Library.
        return {'ok': True, 'library_key': self.library_key, 'stub': False,
                'status': 'repair_existing_library_only'}

    async def verify_library_problem(self, course_id, library_key, problem_id, metadata=None):
        self.check(library_key, problem_id)
        return await self.native.verify_library_problem(course_id, library_key, problem_id, metadata=metadata)

    async def import_problem_to_library(self, course_id, library_key, olx, display_name, metadata=None):
        self.check(library_key)
        question_id = str((metadata or {}).get('question_id') or '')
        if question_id not in self.components:
            raise RuntimeError('Repair refused an unknown question identity')
        component_id = self.components[question_id]
        before = await self.verify_library_problem(course_id, library_key, component_id, metadata)
        if not (before.get('ok') and before.get('problem_exists') and before.get('library_exists', True)):
            raise RuntimeError('Existing CMS component is missing/unverified; stopped before update')
        result = await self.native.import_problem_to_library(
            course_id=course_id, library_key=library_key, olx=literal_olx(olx),
            display_name=display_name, metadata=metadata)
        returned_id = (result.get('openedx_library_problem_id') or result.get('library_problem_id')
                       or result.get('problem_id') or result.get('block_id'))
        if str(returned_id) != component_id or result.get('created') is True:
            raise RuntimeError('Unexpected new/different component; mappings were not replaced')
        return result

    async def delete_library_problem(self, *args, **kwargs):
        # The installed worker may have the old broad rollback. Block it only
        # in this isolated operator process, never call the native delete API.
        raise RuntimeError('Repair preserves existing components; deletion was blocked')


def main():
    from sqlalchemy import text
    from app.core.config import settings
    from app.db.session import SessionLocal, engine
    from app.models.question_bank import (
        BankOperationJob, QuestionBankRelease, QuestionBankVersion,
        Subject, SubjectChapter, SubjectOffering,
    )
    from app.services.bank_operation_jobs import BankOperationJobService
    from app.services.question_bank_service import VersionedQuestionBankService
    from app.services.question_bank import release_publish as workflow_module
    from app.worker import bank_release_publish_task

    if settings.use_mock_openedx or engine.dialect.name != 'postgresql':
        raise RuntimeError('Real PostgreSQL/Open edX runtime required')
    native = workflow_module.get_openedx_connector()

    def no_active(db, release_id):
        active = db.query(BankOperationJob).filter(
            BankOperationJob.release_id == release_id,
            BankOperationJob.operation_type == 'release_publish',
            BankOperationJob.status.in_(['queued', 'running']),
        ).first()
        if active:
            raise RuntimeError(f'Release has active job {active.id}; no retry/reset performed')

    def plan(db):
        offering = db.get(SubjectOffering, OFFERING_ID)
        subject = db.get(Subject, offering.subject_id) if offering else None
        if not subject or subject.code.upper() != 'WEB3023':
            raise RuntimeError('Wrong/missing WEB3023 offering')
        chapters = db.query(SubjectChapter).filter(
            SubjectChapter.subject_offering_id == OFFERING_ID,
            SubjectChapter.status != 'archived',
        ).order_by(SubjectChapter.chapter_no).all()
        if len(chapters) != 8 or [c.chapter_no for c in chapters] != list(range(1, 9)):
            raise RuntimeError('Expected exactly WEB3023 chapters 1–8')
        service = VersionedQuestionBankService(db)
        workflow = service._release_publish_workflow()
        rows = []
        for chapter in chapters:
            release = db.query(QuestionBankRelease).filter(
                QuestionBankRelease.chapter_id == chapter.id,
                QuestionBankRelease.published_at.isnot(None),
                QuestionBankRelease.status.in_(['published', 'publish_failed']),
            ).order_by(QuestionBankRelease.created_at.desc(), QuestionBankRelease.id.desc()).first()
            if not release or release.subject_id != subject.id or chapter.subject_id != subject.id:
                raise RuntimeError(f'Chapter {chapter.chapter_no}: no matching published Release')
            version = db.get(QuestionBankVersion, release.bank_version_id)
            if not version or version.subject_offering_id != OFFERING_ID:
                raise RuntimeError('Bank Version belongs to another offering')
            key = str(release.openedx_library_key or '')
            expected = service.release_library_key(subject=subject, chapter=chapter, version=version)
            if (not key.startswith('lib:') or not service._library_key_same(key, expected)
                    or service._release_library_key_needs_term_upgrade(library_key=key, subject=subject, version=version)):
                raise RuntimeError('Library key would change; no update performed')
            items, _ = workflow._load_frozen_release_snapshot(release)
            components = {str(i.question_id): str(i.openedx_library_problem_id or '') for i in items}
            if not components:
                raise RuntimeError('Empty Release snapshot')
            for qid, cid in components.items():
                if str(uuid.UUID(qid)) != qid or cid != f'lb:{key[4:]}:problem:ai-{qid}':
                    raise RuntimeError('Noncanonical/stale component mapping; no replacement created')
            no_active(db, release.id)
            rows.append({'chapter': chapter.chapter_no, 'release_id': release.id,
                'bank_version_id': version.id, 'library_key': key, 'components': components,
                'course_id': service._release_publish_course_id(release, subject, None)})
        return rows

    async def verify_all(rows):
        for row in rows:
            for cid in row['components'].values():
                verified = await native.verify_library_problem(row['course_id'], row['library_key'], cid)
                if not (verified.get('ok') and verified.get('problem_exists') and verified.get('library_exists', True)):
                    raise RuntimeError(f"Chapter {row['chapter']}: CMS component missing/unverified; stopped")
            print(f"PREFLIGHT Bài {row['chapter']}/8: {len(row['components'])} câu OK", flush=True)

    original_factory = workflow_module.get_openedx_connector
    lock_key = 20261105083023
    with protect_library_identity(VersionedQuestionBankService, workflow_module.QuestionBankReleasePublishWorkflowService), engine.connect() as lock:
        if not lock.execute(text('SELECT pg_try_advisory_lock(:k)'), {'k': lock_key}).scalar():
            raise RuntimeError('Another WEB3023 repair is running')
        lock.commit()
        try:
            with SessionLocal() as db:
                rows = plan(db)
            asyncio.run(verify_all(rows))
            for row in rows:
                with SessionLocal() as db:
                    db.query(QuestionBankRelease).filter(
                        QuestionBankRelease.id == row['release_id']).with_for_update().one()
                    current = next(r for r in plan(db) if r['chapter'] == row['chapter'])
                    if current != row:
                        raise RuntimeError('Scope/mapping changed during execution; stopped')
                    job = BankOperationJobService(db).create_job(
                        operation_type='release_publish', target_type='bank_release',
                        target_id=row['release_id'], release_id=row['release_id'],
                        bank_version_id=row['bank_version_id'], requested_by='k8s-operator:web3023-html-repair',
                        request_json={'force_reimport': True, 'release_id': row['release_id'],
                                      'operator_execution': 'stdin-no-build-existing-only'},
                        progress_total=100, progress_label='K8s: sửa hiển thị WEB3023 tại chỗ')
                    job_id = job.id
                repair = ExistingLibraryRepairConnector(native, row['library_key'], row['components'])
                workflow_module.get_openedx_connector = lambda: repair
                print(f"START Bài {row['chapter']}/8 job={job_id}", flush=True)
                bank_release_publish_task.run(job_id)
                with SessionLocal() as db:
                    job = db.get(BankOperationJob, job_id)
                    if not job or job.status != 'completed' or not (job.result_json or {}).get('ok'):
                        raise RuntimeError(f'Job {job_id} did not complete')
                    print(json.dumps({'chapter': row['chapter'], 'job_id': job_id,
                                      'result': job.result_json}, ensure_ascii=False), flush=True)
            print('DONE 8/8 LIBRARIES. Course copies still require Library sync.', flush=True)
        finally:
            workflow_module.get_openedx_connector = original_factory
            lock.execute(text('SELECT pg_advisory_unlock(:k)'), {'k': lock_key})
            lock.commit()


if __name__ == '__main__':
    main()
