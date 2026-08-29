from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_quiz_workflow_blocks_second_active_instance_for_same_chapter_and_type():
    source = (ROOT / "backend/app/services/question_bank/quiz_creation.py").read_text(encoding="utf-8")
    assert "One active AI-managed assessment per Course + chapter mapping + type" in source
    assert "CourseQuizInstance.status.in_(['creating', 'created', 'published', 'rollback_manual_required'])" in source
    assert "Hãy vào Lịch sử Quiz và bấm Khôi phục" in source


def test_connector_does_not_reuse_existing_quiz_node_by_display_name():
    source = (ROOT / "openedx-connector-plugin/openedx_ai_connector/studio.py").read_text(encoding="utf-8")
    assert "allow_existing: bool = True" in source
    assert "Connector từ chối dùng lại node cũ vì có thể cộng dồn câu hỏi" in source
    assert "allow_existing=False" in source


def test_learning_mfe_and_lms_iframe_exchange_theme_and_resize_messages():
    mfe = (ROOT / "frontend-app-learning-patch/src/courseware/course/sequence/unit-reset/UnitResetButton.jsx").read_text(encoding="utf-8")
    runtime = (ROOT / "openedx-unit-reset-plugin/openedx_unit_reset/views.py").read_text(encoding="utf-8")
    assert "data-paragon-theme-variant" in mfe
    assert "AI_MFE_THEME_SYNC" in mfe
    assert "AI_MFE_REQUEST_RESIZE" in mfe
    assert "AI_QUIZ_IFRAME_READY" in runtime
    assert "type: 'plugin.resize'" in runtime
    assert "scheduleResizeBurst('problem-submit-click')" in runtime
