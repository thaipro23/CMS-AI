from pathlib import Path

release_path = Path('backend/app/services/question_bank/release_publish.py')
text = release_path.read_text()

old = '''    def _release_questions_for_version(self, version: QuestionBankVersion) -> list[Question]:
        return self.db.query(Question).filter(
            Question.bank_version_id == version.id,
            Question.status.in_(['approved', 'published']),
        ).order_by(Question.difficulty.asc(), Question.question_family_id.asc().nullslast(), Question.created_at.asc()).all()

    @staticmethod
    def _release_membership_hash(question_ids: list[str]) -> str:
'''
new = '''    def _release_question_selection(self, version: QuestionBankVersion) -> tuple[list[Question], list[dict]]:
        """Return clean Release membership and an audited exclusion list."""
        candidates = self.db.query(Question).filter(
            Question.bank_version_id == version.id,
            Question.status.in_(['approved', 'published']),
        ).order_by(Question.difficulty.asc(), Question.question_family_id.asc().nullslast(), Question.created_at.asc()).all()
        selected: list[Question] = []
        excluded: list[dict] = []
        seen_lineage: dict[str, str] = {}
        for question in candidates:
            reasons: list[str] = []
            if bool(question.is_retired):
                reasons.append('retired')
            if bool(question.is_duplicate):
                reasons.append('duplicate')
            lineage_root = question_lineage_root(question)
            if not reasons and lineage_root in seen_lineage:
                reasons.append('duplicate_lineage')
            if reasons:
                excluded.append({
                    'question_id': str(question.id),
                    'reasons': reasons,
                    'lineage_root': lineage_root,
                    'kept_question_id': seen_lineage.get(lineage_root),
                })
                continue
            seen_lineage[lineage_root] = str(question.id)
            selected.append(question)
        return selected, excluded

    def _release_questions_for_version(self, version: QuestionBankVersion) -> list[Question]:
        questions, _excluded = self._release_question_selection(version)
        return questions

    def _refresh_unpublished_release_snapshot(self, release: QuestionBankRelease) -> list[dict]:
        """Refresh a pristine unpublished Release from current clean questions."""
        if release.status == 'published' or release.published_at:
            return []
        version = self.db.get(QuestionBankVersion, release.bank_version_id)
        if not version:
            raise ValueError('Release thiếu Bank Version để làm mới snapshot.')
        rows = self.db.query(BankReleaseQuestion).filter(BankReleaseQuestion.bank_release_id == release.id).all()
        if any(bool(row.openedx_library_problem_id) for row in rows):
            return []

        questions, excluded = self._release_question_selection(version)
        if not questions:
            raise ValueError('Không còn câu đã duyệt hợp lệ sau khi tự loại câu lỗi/trùng. Hãy duyệt ít nhất một câu trước khi đưa lên CMS.')

        selected_by_id = {str(question.id): question for question in questions}
        existing_by_id = {str(row.question_id): row for row in rows}
        for question_id, row in list(existing_by_id.items()):
            if question_id not in selected_by_id:
                self.db.delete(row)
                existing_by_id.pop(question_id, None)

        for question in questions:
            question_id = str(question.id)
            row = existing_by_id.get(question_id)
            if row is None:
                row = BankReleaseQuestion(
                    id=str(uuid.uuid4()),
                    bank_release_id=release.id,
                    question_id=question.id,
                    question_family_id=question.question_family_id,
                    difficulty=question.difficulty,
                    openedx_library_problem_id=None,
                )
                self.db.add(row)
                existing_by_id[question_id] = row
            else:
                row.question_family_id = question.question_family_id
                row.difficulty = question.difficulty

        counts = {'easy': 0, 'medium': 0, 'hard': 0}
        families = set()
        for question in questions:
            diff = (question.difficulty or 'easy').lower()
            counts[diff if diff in counts else 'easy'] += 1
            if question.question_family_id:
                families.add(question.question_family_id)
        question_ids = [str(question.id) for question in questions]
        now = datetime.utcnow().isoformat()
        release.status = 'ready'
        release.approved_question_count = len(questions)
        release.easy_count = counts['easy']
        release.medium_count = counts['medium']
        release.hard_count = counts['hard']
        release.family_count = len(families)
        release.metadata_json = {
            **(release.metadata_json or {}),
            'membership_count': len(question_ids),
            'membership_sha256': self._release_membership_hash(question_ids),
            'membership_frozen_at': now,
            'membership_refreshed_before_publish_at': now,
            'auto_excluded_count': len(excluded),
            'auto_excluded_questions': excluded[:100],
            'auto_exclusion_policy': 'draft_error_rejected_not_candidates; duplicate_retired_duplicate_lineage_excluded',
        }
        self.db.flush()
        return excluded

    @staticmethod
    def _release_membership_hash(question_ids: list[str]) -> str:
'''
if old not in text:
    raise SystemExit('release selection marker not found')
text = text.replace(old, new, 1)

old = '''    def _load_frozen_release_snapshot(self, release: QuestionBankRelease) -> tuple[list[BankReleaseQuestion], list[Question]]:
        rows = self.db.query(BankReleaseQuestion).filter(
'''
new = '''    def _load_frozen_release_snapshot(self, release: QuestionBankRelease) -> tuple[list[BankReleaseQuestion], list[Question]]:
        self._refresh_unpublished_release_snapshot(release)
        rows = self.db.query(BankReleaseQuestion).filter(
'''
if old not in text:
    raise SystemExit('frozen snapshot marker not found')
text = text.replace(old, new, 1)

old = "        questions = self._release_questions_for_version(version) if include_approved_questions else []\n"
new = "        questions, auto_excluded = self._release_question_selection(version) if include_approved_questions else ([], [])\n"
if old not in text:
    raise SystemExit('create release selection marker not found')
text = text.replace(old, new, 1)

old = "                'membership_frozen_at': datetime.utcnow().isoformat(),\n"
new = "                'membership_frozen_at': datetime.utcnow().isoformat(),\n                'auto_excluded_count': len(auto_excluded),\n                'auto_excluded_questions': auto_excluded[:100],\n                'auto_exclusion_policy': 'draft_error_rejected_not_candidates; duplicate_retired_duplicate_lineage_excluded',\n"
if old not in text:
    raise SystemExit('release metadata marker not found')
text = text.replace(old, new, 1)

old = "        approved = [q for q in active if q.status in {'approved', 'published'} and not bool(q.is_duplicate)]\n"
new = "        approved, auto_excluded = self._release_question_selection(version)\n"
if old not in text:
    raise SystemExit('readiness approved marker not found')
text = text.replace(old, new, 1)
text = text.replace("        unresolved = pending + draft_error + unknown_status\n", "        unresolved = pending + unknown_status\n", 1)

old = '''        roots: dict[str, int] = {}
        for q in approved:
            root = question_lineage_root(q)
            roots[root] = roots.get(root, 0) + 1
        duplicate_lineage_roots = [root for root, count in roots.items() if count > 1]
'''
new = '''        auto_excluded_duplicates = [item for item in auto_excluded if 'duplicate' in item.get('reasons', []) or 'duplicate_lineage' in item.get('reasons', [])]
        duplicate_lineage_roots = sorted({str(item.get('lineage_root') or '') for item in auto_excluded if 'duplicate_lineage' in item.get('reasons', []) and item.get('lineage_root')})
'''
if old not in text:
    raise SystemExit('readiness lineage marker not found')
text = text.replace(old, new, 1)

old = "            _check('draft_error', 'fail' if draft_error else 'pass', f'Còn {len(draft_error)} câu lỗi. Phải sửa hoặc bỏ hết trước khi chốt bộ đề.' if draft_error else 'Không còn câu lỗi.', {'draft_error_count': len(draft_error)}),\n"
new = "            _check('draft_error', 'warning' if draft_error else 'pass', f'Có {len(draft_error)} câu lỗi; hệ thống sẽ tự loại khỏi Release, không chặn chốt.' if draft_error else 'Không còn câu lỗi.', {'draft_error_count': len(draft_error), 'auto_excluded': True}, blocking=False),\n"
if old not in text:
    raise SystemExit('draft error readiness marker not found')
text = text.replace(old, new, 1)

old = "            _check('duplicate_lineage', 'fail' if duplicate_lineage_roots else 'pass', f'Có {len(duplicate_lineage_roots)} nhóm câu trùng gốc cần xử lý.' if duplicate_lineage_roots else 'Không phát hiện câu trùng gốc trong bộ đã duyệt.', {'duplicate_lineage_roots': duplicate_lineage_roots[:20]}),\n"
new = "            _check('duplicate_lineage', 'warning' if auto_excluded_duplicates else 'pass', f'Có {len(auto_excluded_duplicates)} câu trùng; hệ thống sẽ tự loại khỏi Release.' if auto_excluded_duplicates else 'Không phát hiện câu trùng trong bộ đã duyệt.', {'duplicate_lineage_roots': duplicate_lineage_roots[:20], 'auto_excluded_duplicate_count': len(auto_excluded_duplicates)}, blocking=False),\n"
if old not in text:
    raise SystemExit('duplicate readiness marker not found')
text = text.replace(old, new, 1)

text = text.replace("        if draft_error:\n            actions.append('Sửa hoặc bỏ tất cả câu lỗi trước khi chốt bộ đề.')\n", "        if draft_error:\n            actions.append(f'{len(draft_error)} câu lỗi sẽ tự bị loại khỏi Release; có thể sửa sau nếu muốn dùng lại.')\n", 1)
text = text.replace("        if duplicate_lineage_roots:\n            actions.append('Loại bớt câu trùng gốc để tránh một bộ đề có nhiều câu quá giống nhau.')\n", "        if auto_excluded_duplicates:\n            actions.append(f'{len(auto_excluded_duplicates)} câu trùng sẽ tự bị loại khỏi Release.')\n", 1)
text = text.replace("                'unresolved_count': len(unresolved),\n", "                'unresolved_count': len(unresolved),\n                'auto_excluded_count': len(auto_excluded) + len(draft_error),\n                'auto_excluded_duplicate_count': len(auto_excluded_duplicates),\n", 1)
text = text.replace("            'message': 'Bài đã publish; các thao tác chỉnh sửa đã khóa.' if status == 'published' else ('Đủ điều kiện chốt bộ đề.' if can_create else 'Chưa thể chốt bộ đề. Phải duyệt hoặc bỏ hết tất cả câu hỏi trước.'),\n", "            'message': 'Bài đã publish; các thao tác chỉnh sửa đã khóa.' if status == 'published' else ('Đủ điều kiện chốt bộ đề; câu lỗi/trùng sẽ tự loại.' if can_create else 'Chưa thể chốt bộ đề. Hãy xử lý các câu còn chờ duyệt hoặc trạng thái không xác định.'),\n", 1)
release_path.write_text(text)

generation_path = Path('backend/app/services/question_bank/generation_review.py')
g = generation_path.read_text()
old = "        legacy_fields = {'option_a', 'option_b', 'option_c', 'option_d', 'correct_answer'}\n        legacy_changed = bool(legacy_fields.intersection(data))\n"
new = "        legacy_fields = {'option_a', 'option_b', 'option_c', 'option_d', 'correct_answer'}\n        legacy_changed = bool(legacy_fields.intersection(data))\n        duplicate_sensitive_fields = {'question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_answer'}\n        duplicate_sensitive_changed = requested_type is not None or requested_content is not None or bool(duplicate_sensitive_fields.intersection(data))\n"
if old not in g:
    raise SystemExit('duplicate edit marker not found')
g = g.replace(old, new, 1)
old = "        question.question_hash = question_response_fingerprint(question)\n        if question.status == 'draft_error' and changed:\n"
new = '''        question.question_hash = question_response_fingerprint(question)
        if duplicate_sensitive_changed:
            duplicate = self.db.query(Question).filter(
                Question.bank_version_id == version.id,
                Question.id != question.id,
                Question.question_hash == question.question_hash,
                or_(Question.is_retired.is_(False), Question.is_retired.is_(None)),
                Question.status.notin_(['rejected', 'draft_error']),
            ).order_by(Question.created_at.asc()).first()
            question.is_duplicate = bool(duplicate)
            question.duplicate_of_question_id = str(duplicate.id) if duplicate else None
            question.duplicate_score = 1.0 if duplicate else None
            question.quality_flags = [flag for flag in (question.quality_flags or []) if 'duplicate' not in str(flag).lower() and 'trùng' not in str(flag).lower()]
        if question.status == 'draft_error' and changed:
'''
if old not in g:
    raise SystemExit('question hash marker not found')
g = g.replace(old, new, 1)
generation_path.write_text(g)

page_path = Path('frontend/app/bank/_components/pages/ChapterWorkspacePage.tsx')
p = page_path.read_text()
p = p.replace("title={releaseReviewBlocked ? 'Phải duyệt hoặc bỏ hết tất cả câu hỏi trước khi chốt bộ đề.' : undefined}", "title={releaseReviewBlocked ? 'Còn câu chờ duyệt hoặc trạng thái chưa xác định. Câu lỗi và câu trùng sẽ tự loại khỏi Release.' : undefined}")
p = p.replace("<div className=\"alert warning full-row\"><b>Chưa thể chốt bộ đề.</b> Còn {pendingReviewCount} câu chờ duyệt và {draftErrorCount} câu lỗi. Hãy duyệt hoặc bỏ hết tất cả câu hỏi trước.</div>", "<div className=\"alert warning full-row\"><b>Chưa thể chốt bộ đề.</b> Còn {pendingReviewCount} câu chờ duyệt cần quyết định. {draftErrorCount ? `${draftErrorCount} câu lỗi sẽ tự loại khỏi Release.` : ''}</div>")
p = p.replace("<p>Release sẽ đóng băng toàn bộ câu đã duyệt hiện tại của bài. Sau khi publish, nội dung không chỉnh trực tiếp trên version này.</p>", "<p>Release lấy các câu đã duyệt hợp lệ; câu lỗi, retired và câu trùng được tự loại. Trước lần publish đầu tiên, hệ thống đồng bộ lại snapshot theo các chỉnh sửa mới nhất. Sau khi publish thì version mới bị khóa.</p>")
p = p.replace("<p>Hệ thống sẽ tạo/cập nhật thư viện Open edX từ snapshot Release. Hãy kiểm tra preview và QA bộ đề trước khi tiếp tục.</p>", "<p>Trước khi đưa lên CMS, hệ thống đồng bộ lại Release với các câu đã duyệt hiện tại và tự loại câu lỗi/trùng. Sau đó snapshot mới được publish và khóa.</p>")
page_path.write_text(p)

css_path = Path('frontend/app/globals.css')
css = css_path.read_text()
marker = '/* v25.9.16.7.2.64.16.5.7.2.18 — import overlay hard stop */'
if marker not in css:
    css += r'''

/* v25.9.16.7.2.64.16.5.7.2.18 — import overlay hard stop */
.legacy-quiz-import-page .bank-workflow-stepper,
.legacy-quiz-import-page .legacy-import-preview-heading,
.legacy-quiz-import-page .legacy-import-confirm {
  position: static !important;
  inset: auto !important;
  top: auto !important;
  bottom: auto !important;
  transform: none !important;
}
.legacy-quiz-import-page .bank-workflow-stepper {
  z-index: 1 !important;
  margin: 0 !important;
}
.legacy-quiz-import-page .bank-page-identity {
  position: relative !important;
  z-index: 2;
  margin: 0 !important;
}
.legacy-quiz-import-page > * { min-width: 0; }
'''
css_path.write_text(css)

test_path = Path('backend/app/tests/test_release_snapshot_auto_cleanup.py')
test_path.write_text(r'''from types import SimpleNamespace

from app.services.question_bank.release_publish import QuestionBankReleasePublishWorkflowService


class FakeQuery:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return list(self.rows)


class FakeDB:
    def __init__(self, questions):
        self.questions = questions

    def query(self, model):
        return FakeQuery(self.questions)


class FakeParent:
    def __init__(self, questions):
        self.db = FakeDB(questions)


def q(qid, *, duplicate=False, retired=False, root=None, status='approved'):
    return SimpleNamespace(
        id=qid,
        bank_version_id='v1',
        status=status,
        is_duplicate=duplicate,
        is_retired=retired,
        lineage_root_question_id=root,
        previous_question_id=None,
        difficulty='easy',
        question_family_id=f'family-{qid}',
        created_at=None,
    )


def test_release_selection_auto_excludes_duplicate_retired_and_duplicate_lineage():
    questions = [
        q('good-1', root='root-a'),
        q('same-lineage', root='root-a'),
        q('explicit-duplicate', duplicate=True, root='root-b'),
        q('retired', retired=True, root='root-c'),
        q('good-2', root='root-d'),
    ]
    service = QuestionBankReleasePublishWorkflowService(FakeParent(questions))
    selected, excluded = service._release_question_selection(SimpleNamespace(id='v1'))
    assert [item.id for item in selected] == ['good-1', 'good-2']
    by_id = {item['question_id']: item for item in excluded}
    assert by_id['same-lineage']['reasons'] == ['duplicate_lineage']
    assert by_id['same-lineage']['kept_question_id'] == 'good-1'
    assert by_id['explicit-duplicate']['reasons'] == ['duplicate']
    assert by_id['retired']['reasons'] == ['retired']
''')
