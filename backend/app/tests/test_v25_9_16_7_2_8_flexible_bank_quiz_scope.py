from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_quiz_auto_map_accepts_chapter_plan_and_partial_version_selection():
    schema = (_root() / 'backend' / 'app' / 'schemas' / 'question_bank.py').read_text(encoding='utf-8')
    service = (_root() / 'backend' / 'app' / 'services' / 'question_bank_service.py').read_text(encoding='utf-8')
    route = (_root() / 'backend' / 'app' / 'api' / 'routes' / 'question_bank_v2.py').read_text(encoding='utf-8')

    assert 'class QuizChapterPlanItem(BaseModel):' in schema
    assert "Literal['quiz', 'skip', 'assignment', 'final_test']" in schema
    assert 'chapter_plan: list[QuizChapterPlanItem]' in schema
    assert "Version môn được chọn chưa publish đủ tất cả bài" in service
    assert "selected = candidates[0]['offering']" in service
    assert 'chapter_plan=[item.model_dump() for item in payload.chapter_plan]' in route


def test_quiz_auto_map_skips_assignment_and_final_can_be_explicit():
    service = (_root() / 'backend' / 'app' / 'services' / 'question_bank_service.py').read_text(encoding='utf-8')
    preview = service.split('async def preview_quiz_auto_map', 1)[1].split('async def apply_quiz_auto_map', 1)[0]

    assert "def _quiz_action_for_chapter_title" in service
    assert "return 'assignment'" in service
    assert "return 'skip'" in service
    assert "requires_release = self._quiz_action_requires_release(action)" in preview
    assert "requires_release and not release_info.get('ready')" in preview
    assert "if not requires_release and not section" in preview
    assert "selected_quiz_count" in preview
    assert "skipped_chapter_count" in preview
    assert "recommended_quiz_title': 'Final test' if action == 'final_test'" in preview


def test_apply_saves_only_quiz_final_rows_and_preserves_skipped_rows():
    service = (_root() / 'backend' / 'app' / 'services' / 'question_bank_service.py').read_text(encoding='utf-8')
    apply = service.split('async def apply_quiz_auto_map', 1)[1].split('def _validation_result', 1)[0]

    assert "if not item.get('requires_quiz')" in apply
    assert "mapping_status': 'skipped_no_quiz'" in apply
    assert "if not item.get('ready')" in apply
    assert "Đã lưu cấu hình version" in apply


def test_create_quiz_respects_final_test_title_and_assessment_type():
    schema = (_root() / 'backend' / 'app' / 'schemas' / 'question_bank.py').read_text(encoding='utf-8')
    service = (_root() / 'backend' / 'app' / 'services' / 'question_bank_service.py').read_text(encoding='utf-8')
    worker = (_root() / 'backend' / 'app' / 'worker.py').read_text(encoding='utf-8')
    api = (_root() / 'frontend' / 'lib' / 'api.ts').read_text(encoding='utf-8')

    assert "assessment_type: Literal['quiz', 'final_test'] = 'quiz'" in schema
    assert "assessment_type: str = 'quiz'" in service
    assert "default_quiz_title = 'Final test' if assessment_type == 'final_test'" in service
    assert "grade_as = 'Final Exam' if assessment_type == 'final_test' else 'Quiz'" in service
    assert "'assessment_type': assessment_type" in service
    assert "assessment_type=str(payload.get('assessment_type') or 'quiz')" in worker
    assert "assessment_type?: 'quiz' | 'final_test'" in api


def test_bank_quiz_frontend_has_action_selector_and_separate_final_config():
    page = (_root() / 'frontend' / 'app' / 'bank' / 'quiz' / 'page.tsx').read_text(encoding='utf-8')

    assert "QuizChapterAction" in page
    assert "Tạo Final test" in page
    assert "Assignment/nội dung" not in page
    assert "Không tạo" in page
    assert "finalConfig" in page
    assert "quizConfig" in page
    assert "chapter_plan: actionPlan" in page
    assert "assessment_type: item.action === 'final_test' ? 'final_test' : 'quiz'" in page
    assert "item.metadata_json?.assessment_type === 'final_test'" in page
