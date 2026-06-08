from app.services.question_bank_service import parse_openedx_course_id, slugify
from app.services.question_bank_service import chunk_policy_for_material_source
from app.services.generation_cache import question_fingerprint


def test_bank_material_chunk_policy_prefers_small_chunks_for_documents():
    assert chunk_policy_for_material_source('pdf') == (1000, 120)
    assert chunk_policy_for_material_source('xlsx') == (1100, 80)


def test_bank_question_fingerprint_is_scoped_by_bank_version_family():
    left = question_fingerprint('Câu hỏi mẫu?', course_id='bank:version-a', source_node_id='family-a', difficulty='easy')
    right = question_fingerprint('Câu hỏi mẫu?', course_id='bank:version-b', source_node_id='family-a', difficulty='easy')
    assert left != right


def test_slugify_keeps_release_safe_ids():
    assert slugify('DOM123 Bài 4 v1.0') == 'dom123-bai-4-v1-0'
