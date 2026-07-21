from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_quiz_create_uses_stable_slot_idempotency_key_and_legacy_partial_recovery():
    source = (ROOT / "backend/app/services/question_bank/quiz_creation.py").read_text(encoding="utf-8")
    assert "quiz_idempotency_key = f'course_quiz:{chapter_mapping.id}:{assessment_type}'" in source
    assert "'recover_empty_legacy_partial': True" in source
    assert "'idempotency_key': quiz_idempotency_key" in source


def test_connector_reuses_only_idempotent_or_empty_partial_nodes():
    source = (ROOT / "openedx-connector-plugin/openedx_ai_connector/studio.py").read_text(encoding="utf-8")
    assert "class QuizNodeConflictError(ValueError)" in source
    assert "def _is_recoverable_empty_quiz_partial" in source
    assert "reuse_idempotent_existing_child" in source
    assert "recover_empty_legacy_partial_child" in source
    assert "existing_child_count" in source
    assert "quiz_node_conflict" in source


def test_connector_returns_request_id_for_create_quiz_failures():
    source = (ROOT / "openedx-connector-plugin/openedx_ai_connector/studio.py").read_text(encoding="utf-8")
    assert "def _connector_request_id" in source
    assert "'request_id': request_id" in source
    assert "create_quiz_node validation failed request_id=%s" in source
