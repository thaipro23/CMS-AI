from app.algorithms.largest_remainder import allocate_by_largest_remainder
from app.services.answer_randomizer import normalize_and_shuffle_options
from app.services.quality_checker import QualityChecker
from app.services.question_diversity import diversity_report


class DummyQuestion:
    def __init__(self, id, text, status='pending_review', difficulty='easy'):
        self.id = id
        self.question_text = text
        self.status = status
        self.difficulty = difficulty


def test_largest_remainder_default_20_questions():
    rows = allocate_by_largest_remainder(20, {'easy': 50, 'medium': 30, 'hard': 20})
    assert {row.difficulty: row.question_count for row in rows} == {'easy': 10, 'medium': 6, 'hard': 4}


def test_largest_remainder_rounds_missing_to_largest_remainder():
    rows = allocate_by_largest_remainder(7, {'easy': 50, 'medium': 30, 'hard': 20})
    assert {row.difficulty: row.question_count for row in rows} == {'easy': 4, 'medium': 2, 'hard': 1}


def test_answer_randomizer_keeps_correct_text_and_changes_position():
    item = {
        'question': 'Entity Framework Core là gì?',
        'options': {'A': 'ORM của .NET', 'B': 'Hệ điều hành', 'C': 'Trình duyệt', 'D': 'Công cụ UI'},
        'correct_answer': 'A',
        'source_node_id': 'node-1',
        'difficulty': 'easy',
    }
    result = normalize_and_shuffle_options(item, index=3)
    assert result.options[result.correct_answer] == 'ORM của .NET'
    assert set(result.options.keys()) == {'A', 'B', 'C', 'D'}


def test_quality_checker_returns_error_code():
    item = {
        'question': 'Entity Framework Core là gì?',
        'options': {'A': 'ORM', 'B': 'ORM', 'C': 'SQL Server', 'D': 'UI'},
        'correct_answer': 'A',
        'source_ref': 'slide:1',
        'explanation': 'test',
    }
    result = QualityChecker().check(item)
    assert result.passed is False
    assert result.error_code == 'duplicate_options'


def test_diversity_report_detects_repeated_concept():
    rows = [
        DummyQuestion('1', 'Entity Framework Core là gì?'),
        DummyQuestion('2', 'Entity Framework Core được mô tả là gì?'),
        DummyQuestion('3', 'Lệnh Add-Migration dùng để làm gì?'),
        DummyQuestion('4', 'Lệnh Add-Migration tạo gì?'),
    ]
    report = diversity_report(rows)  # type: ignore[arg-type]
    assert report['total_questions'] == 4
    assert report['concept_count'] >= 2


def test_output_token_defaults_are_safe():
    from app.services.token_calibration import DEFAULT_OUTPUT_TOKENS_PER_QUESTION
    assert DEFAULT_OUTPUT_TOKENS_PER_QUESTION['easy'] >= 650
    assert DEFAULT_OUTPUT_TOKENS_PER_QUESTION['medium'] >= 750
    assert DEFAULT_OUTPUT_TOKENS_PER_QUESTION['hard'] >= 900


def test_tail_remainders_keep_one_prompt_per_difficulty():
    from app.services.generation_planner import _difficulty_work_items

    items = _difficulty_work_items(
        course_id='course-v1:Demo+DOM1051+2026',
        content='REST API content ' * 200,
        total_questions=50,
        scope_title='Chapter 1 - REST API',
        content_tokens=1200,
        chunk_ids=['chunk-1'],
        node_id='chapter-1',
        percentages={'easy': 50, 'medium': 30, 'hard': 20},
        max_batch_size=12,
    )
    primary = [item for item in items if item['phase'] == 'primary']
    tail = [item for item in items if item['phase'] == 'tail']

    assert [(item['target_difficulty'], item['question_count']) for item in primary] == [
        ('easy', 12),
        ('easy', 12),
        ('medium', 12),
        ('hard', 10),
    ]
    assert [(item['target_difficulty'], item['question_count'], item['difficulty_counts']) for item in tail] == [
        ('easy', 1, {'easy': 1}),
        ('medium', 3, {'medium': 3}),
    ]
    assert all(item['prompt_cache_key'] == items[0]['prompt_cache_key'] for item in items)


def test_cache_warmup_picks_one_small_batch_per_prompt_prefix(monkeypatch):
    from app import worker

    monkeypatch.setattr(worker.settings, 'openai_prompt_cache_warmup_enabled', True)
    items = [
        {'prompt_cache_key': 'same-prefix', 'question_count': 12, 'batch_index': 1},
        {'prompt_cache_key': 'same-prefix', 'question_count': 10, 'batch_index': 2},
        {'prompt_cache_key': 'same-prefix', 'question_count': 12, 'batch_index': 3},
        {'prompt_cache_key': 'other-prefix', 'question_count': 7, 'batch_index': 4},
        {'prompt_cache_key': 'other-prefix', 'question_count': 3, 'batch_index': 5},
    ]
    warmups, remaining = worker._split_cache_warmup_items(items)

    assert [item['question_count'] for item in warmups] == [10, 3]
    assert len(remaining) == 3


def test_node_coverage_uses_weighted_teachable_content_and_skips_intro_chunks():
    from app.algorithms.node_coverage import NodeCoverageAllocator, content_signal

    assert content_signal('Giới thiệu môn học. Lịch học. Hình thức đánh giá.', 40, title='Giới thiệu môn học').teachable is False
    lesson = 'REST API là kiến trúc giao tiếp dùng HTTP request và response. Ví dụ GET dùng để lấy dữ liệu, POST dùng để tạo dữ liệu mới. Client gửi request đến server và server trả response phù hợp.'
    assert content_signal(lesson, 160, title='REST API').teachable is True

    allocations = NodeCoverageAllocator().allocate([
        {'node_id': 'intro', 'title': 'Giới thiệu', 'block_type': 'chapter', 'chunk_count': 1, 'token_count': 80, 'teachable_chunk_count': 0, 'effective_token_count': 0},
        {'node_id': 'rest', 'title': 'REST API', 'block_type': 'chapter', 'chunk_count': 3, 'token_count': 1000, 'teachable_chunk_count': 3, 'effective_token_count': 1000},
        {'node_id': 'auth', 'title': 'Authentication', 'block_type': 'chapter', 'chunk_count': 1, 'token_count': 250, 'teachable_chunk_count': 1, 'effective_token_count': 250},
    ], 10)

    quotas = {row.node_id: row.question_quota for row in allocations}
    assert 'intro' not in quotas
    assert quotas['rest'] > quotas['auth']
    assert sum(quotas.values()) == 10


def test_audit_error_type_is_normalized_to_uppercase():
    from app.services.audit_log import AuditErrorType, normalize_error_type

    assert normalize_error_type('user') == AuditErrorType.USER_ERROR
    assert normalize_error_type('system') == AuditErrorType.SYSTEM_ERROR
    assert normalize_error_type('external') == AuditErrorType.EXTERNAL_SERVICE_ERROR
    assert normalize_error_type('validation_error') == AuditErrorType.VALIDATION_ERROR
    assert normalize_error_type('AUTH_ERROR') == AuditErrorType.AUTH_ERROR



def test_problem_xml_parser_preserves_correct_answer_and_removes_filename_metadata():
    from app.services.content_extractor import ContentExtractor

    xml = '<problem><multiplechoiceresponse><label>Website được xây dựng trên một hay nhiều ngôn ngữ lập trình?</label><choicegroup type="MultipleChoice"><choice correct="false">Một và chỉ một ngôn ngữ duy nhất</choice><choice correct="true">Có thể xây dựng bằng nhiều ngôn ngữ lập trình khác nhau</choice><choice correct="false">Không cần ngôn ngữ lập trình</choice></choicegroup></multiplechoiceresponse></problem> {"filename": ["problem/old.xml"]}'
    items = ContentExtractor().extract_block({
        'block_id': 'problem-old',
        'type': 'problem',
        'display_name': 'Trắc nghiệm cuối bài',
        'data': xml,
    })

    assert len(items) == 1
    content = items[0].content
    assert 'filename' not in content
    assert 'Câu 1: Website được xây dựng' in content
    assert 'Có thể xây dựng bằng nhiều ngôn ngữ lập trình khác nhau [ĐÁP ÁN ĐÚNG]' in content



def test_poly_problem_xml_parser_handles_prompt_outside_multiplechoiceresponse():
    from app.services.content_extractor import ContentExtractor
    from app.services.problem_parser import parse_problem_xml

    xml = """<problem>
  <div class="poly">
    <h3 id="Q09x04">CÂU 1:</h3>
    <pre class="poly-body">Website được xây dựng trên một hay nhiều ngôn ngữ lập trình ?</pre>
    <div><i>Chọn một đáp án đúng</i></div>
  </div>
  <multiplechoiceresponse>
    <choicegroup type="MultipleChoice">
      <choice correct="false">Một và chỉ một ngôn ngữ duy nhất</choice>
      <choice correct="true">Có thể xây dựng bằng nhiều ngôn ngữ lập trình khác nhau</choice>
      <choice correct="false">Có thể xây dựng website bằng 2 ngôn ngữ lập trình</choice>
      <choice correct="false">Không cần ngôn ngữ lập trình nào cũng có thể xây dựng website</choice>
    </choicegroup>
  </multiplechoiceresponse>
  <div class="poly">
    <h3 id="Q09x02">CÂU 2:</h3>
    <pre class="poly-body">Website động và website tĩnh khác nhau như thế nào?</pre>
  </div>
  <multiplechoiceresponse>
    <choicegroup type="MultipleChoice">
      <choice correct="false">Không khác nhau</choice>
      <choice correct="true">Website động có thêm các phần xử lý thông tin và truy xuất dữ liệu còn website tĩnh thì không.</choice>
      <choice correct="false">Website tĩnh luôn tốt hơn website động</choice>
      <choice correct="false">Website động không cần dữ liệu</choice>
    </choicegroup>
  </multiplechoiceresponse>
</problem>

Trắc nghiệm cuối bài
{"filename": ["problem/caafedd348ef483c89e04ec93063f9aa.xml"]}"""

    parsed = parse_problem_xml(xml)
    assert len(parsed) == 2
    assert parsed[0].question == 'CÂU 1: Website được xây dựng trên một hay nhiều ngôn ngữ lập trình ?'
    assert parsed[0].choices[1].correct is True
    assert parsed[1].question == 'CÂU 2: Website động và website tĩnh khác nhau như thế nào?'
    assert parsed[1].choices[1].correct is True

    items = ContentExtractor().extract_block({
        'block_id': 'problem-poly',
        'type': 'problem',
        'display_name': 'Trắc nghiệm cuối bài',
        'problem_xml': xml,
    })
    content = items[0].content
    assert 'filename' not in content
    assert 'CÂU 1: Website được xây dựng' in content
    assert 'Có thể xây dựng bằng nhiều ngôn ngữ lập trình khác nhau [ĐÁP ÁN ĐÚNG]' in content
    assert 'CÂU 2: Website động và website tĩnh khác nhau như thế nào?' in content


def test_generation_query_allows_problem_chunks_as_rewrite_source_inside_selected_scope():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.session import Base
    from app.models.course import ContentChunk, CourseSyncState
    from app.services.generation_planner import query_chunks

    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        course_id = 'course-v1:TEST+WEB+SU26'
        db.add_all([
            CourseSyncState(course_id=course_id, block_id='chapter-1', block_type='chapter', display_name='Bài 1'),
            CourseSyncState(course_id=course_id, block_id='html-1', parent_block_id='chapter-1', block_type='html', display_name='HTML'),
            CourseSyncState(course_id=course_id, block_id='problem-1', parent_block_id='chapter-1', block_type='problem', display_name='Quiz cũ'),
            ContentChunk(course_id=course_id, block_id='html-1', source_type='html', content='HTML learning content', token_count=120),
            ContentChunk(course_id=course_id, block_id='problem-1', source_type='problem', content='Old quiz [ĐÁP ÁN ĐÚNG]', token_count=80),
        ])
        db.commit()

        default_chunks = query_chunks(db, course_id)
        assert [chunk.source_type for chunk in default_chunks] == ['html', 'problem']

        chapter_chunks = query_chunks(db, course_id, node_ids=['chapter-1'])
        assert [chunk.source_type for chunk in chapter_chunks] == ['html', 'problem']

        explicit_problem_chunks = query_chunks(db, course_id, node_ids=['problem-1'])
        assert [chunk.source_type for chunk in explicit_problem_chunks] == ['problem']

        explicit_chunk = query_chunks(db, course_id, chunk_ids=[explicit_problem_chunks[0].id])
        assert [chunk.source_type for chunk in explicit_chunk] == ['problem']
    finally:
        db.close()



def test_quality_checker_rejects_direct_copy_from_old_problem():
    from app.services.quality_checker import QualityChecker

    checker = QualityChecker()
    item = {
        'question': 'Website được xây dựng trên một hay nhiều ngôn ngữ lập trình?',
        'options': {
            'A': 'Một và chỉ một ngôn ngữ duy nhất',
            'B': 'Có thể xây dựng bằng nhiều ngôn ngữ lập trình khác nhau',
            'C': 'Có thể xây dựng website bằng 2 ngôn ngữ lập trình',
            'D': 'Không cần ngôn ngữ lập trình nào cũng có thể xây dựng website',
        },
        'correct_answer': 'B',
        'explanation': 'Website có thể dùng nhiều ngôn ngữ lập trình khác nhau.',
        'source_ref': 'problem-old',
        'source_type': 'problem',
        'source_excerpt': 'Câu 1: Website được xây dựng trên một hay nhiều ngôn ngữ lập trình?\nA. Một và chỉ một ngôn ngữ duy nhất\nB. Có thể xây dựng bằng nhiều ngôn ngữ lập trình khác nhau [ĐÁP ÁN ĐÚNG]',
    }

    result = checker.check(item)
    assert not result.passed
    assert result.error_code == 'old_problem_copy'


def test_quality_checker_allows_rewritten_problem_question():
    from app.services.quality_checker import QualityChecker

    checker = QualityChecker()
    item = {
        'question': 'Khi phát triển một website thực tế, nhận định nào đúng nhất về việc sử dụng ngôn ngữ lập trình?',
        'options': {
            'A': 'Website có thể kết hợp nhiều ngôn ngữ/công nghệ khác nhau để xây dựng chức năng',
            'B': 'Mỗi website bắt buộc chỉ dùng đúng một ngôn ngữ duy nhất',
            'C': 'Website không bao giờ cần ngôn ngữ lập trình',
            'D': 'Website chỉ được dùng hai ngôn ngữ và không được nhiều hơn',
        },
        'correct_answer': 'A',
        'explanation': 'Website thực tế có thể kết hợp nhiều ngôn ngữ và công nghệ.',
        'source_ref': 'problem-old',
        'source_type': 'problem',
        'source_excerpt': 'Câu 1: Website được xây dựng trên một hay nhiều ngôn ngữ lập trình?\nA. Một và chỉ một ngôn ngữ duy nhất\nB. Có thể xây dựng bằng nhiều ngôn ngữ lập trình khác nhau [ĐÁP ÁN ĐÚNG]',
    }

    result = checker.check(item)
    assert result.passed



def test_generation_query_does_not_silently_limit_full_node_content():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.session import Base
    from app.models.course import ContentChunk, CourseSyncState
    from app.services.generation_planner import query_chunks

    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        course_id = 'course-v1:TEST+FULL+SU26'
        db.add(CourseSyncState(course_id=course_id, block_id='chapter-full', block_type='chapter', display_name='Bài full'))
        for index in range(55):
            block_id = f'html-{index:02d}'
            db.add(CourseSyncState(course_id=course_id, block_id=block_id, parent_block_id='chapter-full', block_type='html', display_name=block_id))
            db.add(ContentChunk(course_id=course_id, block_id=block_id, source_type='html', content=f'Nội dung học liệu {index}', token_count=50))
        db.commit()

        chunks = query_chunks(db, course_id, node_ids=['chapter-full'])
        assert len(chunks) == 55
        assert chunks[0].content == 'Nội dung học liệu 0'
        assert chunks[-1].content == 'Nội dung học liệu 54'
    finally:
        db.close()
