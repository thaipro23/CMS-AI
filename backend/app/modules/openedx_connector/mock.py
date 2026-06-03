from app.modules.openedx_connector.base import OpenEdXConnector


class MockOpenEdXConnector(OpenEdXConnector):
    """Rich v19 mock Open edX connector.

    This mock is intentionally close to a real Open edX course shape:
    Course -> Chapter -> Sequential -> Vertical -> Component.

    It provides enough data to validate v19 algorithms:
    - course tree traversal via children/parent_block_id;
    - HTML/transcript/file/problem extraction;
    - topic extraction and topic coverage;
    - source grounding with page/timestamp/source_ref;
    - duplicate detection using generated question variants.
    """

    async def get_course_blocks(self, course_id: str) -> list[dict]:
        def bid(block_type: str, name: str) -> str:
            return f'{course_id}+type@{block_type}+block@{name}'

        course = bid('course', 'ai-learning-check-demo')

        # Chapter 1: REST API basics
        ch_rest = bid('chapter', 'chapter-rest-api')
        seq_rest_intro = bid('sequential', 'seq-rest-intro')
        unit_rest_overview = bid('vertical', 'unit-rest-overview')
        unit_http_methods = bid('vertical', 'unit-http-methods')
        html_rest_overview = bid('html', 'html-rest-overview')
        video_http_methods = bid('video', 'video-http-methods')
        problem_http_old = bid('problem', 'problem-http-old')

        # Chapter 2: EF Core basics
        ch_ef = bid('chapter', 'chapter-ef-core')
        seq_ef = bid('sequential', 'seq-ef-core-foundation')
        unit_dbcontext = bid('vertical', 'unit-dbcontext')
        unit_migration = bid('vertical', 'unit-migration')
        html_dbcontext = bid('html', 'html-dbcontext')
        video_migration = bid('video', 'video-migration')
        problem_ef_old = bid('problem', 'problem-ef-old')

        # Chapter 3: AI Server workflow and cost control
        ch_ai = bid('chapter', 'chapter-ai-server')
        seq_ai = bid('sequential', 'seq-ai-pipeline')
        unit_sync = bid('vertical', 'unit-course-sync')
        unit_cost = bid('vertical', 'unit-cost-control')
        html_sync = bid('html', 'html-course-sync')
        html_cost = bid('html', 'html-cost-control')
        video_review = bid('video', 'video-review-workflow')
        problem_ai_old = bid('problem', 'problem-ai-old')

        return [
            {
                'block_id': course,
                'type': 'course',
                'display_name': 'AI Learning Check Demo Course',
                'children': [ch_rest, ch_ef, ch_ai],
                'metadata': {
                    'org': 'FPT-Poly',
                    'language': 'vi',
                    'learning_outcomes': [
                        'Hiểu REST API và HTTP methods cơ bản.',
                        'Nhận biết vai trò DbContext và Migration trong EF Core.',
                        'Hiểu luồng AI Server tạo Learning Check từ Open edX course.',
                    ],
                },
            },
            {
                'block_id': ch_rest,
                'type': 'chapter',
                'display_name': 'Chương 1: REST API cơ bản',
                'parent_block_id': course,
                'children': [seq_rest_intro],
                'data': 'Chương này giới thiệu REST API, tài nguyên, HTTP methods và cách dùng GET, POST, PUT, DELETE trong API.',
            },
            {
                'block_id': seq_rest_intro,
                'type': 'sequential',
                'display_name': 'Bài 1: HTTP Methods trong REST API',
                'parent_block_id': ch_rest,
                'children': [unit_rest_overview, unit_http_methods],
                'data': 'Bài học giúp sinh viên nhận biết method HTTP phù hợp cho từng thao tác với tài nguyên.',
            },
            {
                'block_id': unit_rest_overview,
                'type': 'vertical',
                'display_name': 'Unit 1.1: Tổng quan REST API',
                'parent_block_id': seq_rest_intro,
                'children': [html_rest_overview],
                'data': 'REST API tổ chức dữ liệu theo tài nguyên. Client gửi request đến endpoint để thao tác với tài nguyên.',
            },
            {
                'block_id': html_rest_overview,
                'type': 'html',
                'display_name': 'Reading: REST API overview',
                'parent_block_id': unit_rest_overview,
                'source_ref': f'{html_rest_overview}#html',
                'data': '''
                    <h2>REST API</h2>
                    <p>REST API là phong cách thiết kế API dựa trên tài nguyên.</p>
                    <p>Endpoint thường đại diện cho một tài nguyên, ví dụ /api/products hoặc /api/orders.</p>
                    <p>Client dùng HTTP request để yêu cầu server trả về dữ liệu hoặc thay đổi dữ liệu.</p>
                    <p>Câu hỏi Learning Check chỉ kiểm tra nội dung sinh viên đã đọc, không đánh đố.</p>
                ''',
                'assets': [
                    {
                        'asset_id': f'{course_id}/assets/rest-api-slide.pdf',
                        'file_name': 'REST_API_Overview.pdf',
                        'mime_type': 'application/pdf',
                        'text': 'Slide 1: REST API dựa trên tài nguyên. Slide 2: Endpoint là đường dẫn đại diện tài nguyên. Slide 3: Client gửi request và server trả response. Slide 4: REST dùng HTTP methods để thao tác tài nguyên.',
                    }
                ],
            },
            {
                'block_id': unit_http_methods,
                'type': 'vertical',
                'display_name': 'Unit 1.2: GET POST PUT DELETE',
                'parent_block_id': seq_rest_intro,
                'children': [video_http_methods, problem_http_old],
                'data': 'Unit này giải thích HTTP methods. GET lấy dữ liệu. POST tạo mới. PUT cập nhật. DELETE xóa dữ liệu.',
            },
            {
                'block_id': video_http_methods,
                'type': 'video',
                'display_name': 'Video: HTTP Methods',
                'parent_block_id': unit_http_methods,
                'source_ref': f'{video_http_methods}#video',
                'data': 'Video giới thiệu GET, POST, PUT, DELETE trong REST API.',
                'transcripts': [
                    {
                        'block_id': f'{video_http_methods}:transcript-vi-1',
                        'display_name': 'Transcript VI - HTTP Methods phần 1',
                        'content': '''
                            1
                            00:00:10,000 --> 00:00:25,000
                            GET thường được dùng để lấy dữ liệu từ server mà không làm thay đổi dữ liệu.

                            2
                            00:00:26,000 --> 00:00:40,000
                            POST thường được dùng để gửi dữ liệu lên server nhằm tạo mới tài nguyên.
                        ''',
                        'timestamp_start': '00:00:10',
                        'timestamp_end': '00:00:40',
                        'source_ref': f'{video_http_methods}:transcript-vi-1',
                    },
                    {
                        'block_id': f'{video_http_methods}:transcript-vi-2',
                        'display_name': 'Transcript VI - HTTP Methods phần 2',
                        'content': '''
                            3
                            00:00:41,000 --> 00:01:05,000
                            PUT thường được dùng để cập nhật toàn bộ tài nguyên theo dữ liệu gửi lên.

                            4
                            00:01:06,000 --> 00:01:25,000
                            DELETE thường được dùng để xóa một tài nguyên trên server.
                        ''',
                        'timestamp_start': '00:00:41',
                        'timestamp_end': '00:01:25',
                        'source_ref': f'{video_http_methods}:transcript-vi-2',
                    },
                ],
            },
            {
                'block_id': problem_http_old,
                'type': 'problem',
                'display_name': 'Quiz cũ: HTTP Methods',
                'parent_block_id': unit_http_methods,
                'source_ref': f'{problem_http_old}#old-problem',
                'data': '<problem><multiplechoiceresponse><label>Method nào thường dùng để lấy dữ liệu?</label><choicegroup><choice correct="true">GET</choice><choice correct="false">POST</choice></choicegroup></multiplechoiceresponse></problem>',
            },
            {
                'block_id': ch_ef,
                'type': 'chapter',
                'display_name': 'Chương 2: Entity Framework Core',
                'parent_block_id': course,
                'children': [seq_ef],
                'data': 'Chương này giới thiệu Entity Framework Core, DbContext, DbSet và Migration trong ứng dụng .NET.',
            },
            {
                'block_id': seq_ef,
                'type': 'sequential',
                'display_name': 'Bài 2: DbContext và Migration',
                'parent_block_id': ch_ef,
                'children': [unit_dbcontext, unit_migration],
                'data': 'Bài học giúp sinh viên nhận biết vai trò của DbContext và Migration trong EF Core.',
            },
            {
                'block_id': unit_dbcontext,
                'type': 'vertical',
                'display_name': 'Unit 2.1: DbContext và DbSet',
                'parent_block_id': seq_ef,
                'children': [html_dbcontext],
                'data': 'DbContext là lớp trung tâm trong EF Core, quản lý kết nối database và theo dõi entity.',
            },
            {
                'block_id': html_dbcontext,
                'type': 'html',
                'display_name': 'Reading: DbContext trong EF Core',
                'parent_block_id': unit_dbcontext,
                'source_ref': f'{html_dbcontext}#html',
                'data': '''
                    <h2>Entity Framework Core</h2>
                    <p>Entity Framework Core là ORM của .NET giúp ánh xạ object với bảng trong database.</p>
                    <p>DbContext dùng để cấu hình kết nối database, quản lý DbSet và theo dõi thay đổi của entity.</p>
                    <p>DbSet đại diện cho một tập entity, thường tương ứng với một bảng trong database.</p>
                    <p>Khi gọi SaveChanges, EF Core ghi các thay đổi đang theo dõi xuống database.</p>
                ''',
                'assets': [
                    {
                        'asset_id': f'{course_id}/assets/ef-core-slide.pptx',
                        'file_name': 'EF_Core_DbContext.pptx',
                        'mime_type': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                        'text': 'Slide 1: Entity Framework Core là ORM của .NET. Slide 2: DbContext quản lý kết nối và entity. Slide 3: DbSet đại diện bảng dữ liệu. Slide 4: SaveChanges ghi thay đổi xuống database.',
                    }
                ],
            },
            {
                'block_id': unit_migration,
                'type': 'vertical',
                'display_name': 'Unit 2.2: Migration',
                'parent_block_id': seq_ef,
                'children': [video_migration, problem_ef_old],
                'data': 'Migration dùng để tạo và cập nhật schema database theo model trong code.',
            },
            {
                'block_id': video_migration,
                'type': 'video',
                'display_name': 'Video: Migration trong EF Core',
                'parent_block_id': unit_migration,
                'source_ref': f'{video_migration}#video',
                'data': 'Video giải thích Migration và lệnh cập nhật database.',
                'transcripts': [
                    {
                        'block_id': f'{video_migration}:transcript-vi-1',
                        'display_name': 'Transcript VI - Migration',
                        'content': '''
                            1
                            00:00:05,000 --> 00:00:25,000
                            Migration trong EF Core dùng để tạo lịch sử thay đổi schema database.

                            2
                            00:00:26,000 --> 00:00:45,000
                            Add-Migration tạo file migration mới dựa trên sự thay đổi của model.

                            3
                            00:00:46,000 --> 00:01:05,000
                            Update-Database áp dụng migration để cập nhật schema trong database.
                        ''',
                        'timestamp_start': '00:00:05',
                        'timestamp_end': '00:01:05',
                        'source_ref': f'{video_migration}:transcript-vi-1',
                    }
                ],
            },
            {
                'block_id': problem_ef_old,
                'type': 'problem',
                'display_name': 'Quiz cũ: EF Core',
                'parent_block_id': unit_migration,
                'source_ref': f'{problem_ef_old}#old-problem',
                'data': '<problem><multiplechoiceresponse><label>DbContext dùng để làm gì?</label><choicegroup><choice correct="true">Quản lý kết nối database và entity</choice><choice correct="false">Thiết kế giao diện</choice></choicegroup></multiplechoiceresponse></problem>',
            },
            {
                'block_id': ch_ai,
                'type': 'chapter',
                'display_name': 'Chương 3: AI Server cho Open edX',
                'parent_block_id': course,
                'children': [seq_ai],
                'data': 'Chương này mô tả AI Server, Course Sync, Question Bank, Teacher Review, Cost Control và Publish sang Open edX.',
            },
            {
                'block_id': seq_ai,
                'type': 'sequential',
                'display_name': 'Bài 3: Luồng AI Learning Check',
                'parent_block_id': ch_ai,
                'children': [unit_sync, unit_cost],
                'data': 'Bài học giải thích cách AI Server lấy nội dung course, chia chunk, sinh câu hỏi và kiểm soát chi phí.',
            },
            {
                'block_id': unit_sync,
                'type': 'vertical',
                'display_name': 'Unit 3.1: Course Sync và Question Bank',
                'parent_block_id': seq_ai,
                'children': [html_sync, video_review, problem_ai_old],
                'data': 'Course Sync lấy nội dung từ Open edX, lưu chunk có source reference và đưa câu hỏi vào Teacher Review.',
            },
            {
                'block_id': html_sync,
                'type': 'html',
                'display_name': 'Reading: Course Sync Pipeline',
                'parent_block_id': unit_sync,
                'source_ref': f'{html_sync}#html',
                'data': '''
                    <h2>Course Sync Pipeline</h2>
                    <p>AI Server không yêu cầu giáo viên upload lại tài liệu.</p>
                    <p>Course Content Connector lấy course outline, HTML, transcript, file PDF/PPTX và quiz cũ từ Open edX.</p>
                    <p>Nội dung được chia thành chunk có source reference để phục vụ source grounding.</p>
                    <p>Câu hỏi AI sinh ra đi vào Teacher Review Queue trước khi được approve hoặc reject.</p>
                    <p>Question Bank lưu câu hỏi theo course, topic, difficulty, source và trạng thái.</p>
                ''',
            },
            {
                'block_id': video_review,
                'type': 'video',
                'display_name': 'Video: Teacher Review Workflow',
                'parent_block_id': unit_sync,
                'source_ref': f'{video_review}#video',
                'data': 'Video giới thiệu Teacher Review Queue và Question Bank.',
                'transcripts': [
                    {
                        'block_id': f'{video_review}:transcript-vi-1',
                        'display_name': 'Transcript VI - Review Workflow',
                        'content': '''
                            1
                            00:00:10,000 --> 00:00:30,000
                            AI-generated question mặc định không publish trực tiếp cho sinh viên.

                            2
                            00:00:31,000 --> 00:00:55,000
                            Giáo viên cần review, edit, approve hoặc reject câu hỏi trước khi đưa vào quiz.

                            3
                            00:00:56,000 --> 00:01:10,000
                            Câu hỏi approved có thể export thành Open edX OLX XML hoặc publish qua connector.
                        ''',
                        'timestamp_start': '00:00:10',
                        'timestamp_end': '00:01:10',
                        'source_ref': f'{video_review}:transcript-vi-1',
                    }
                ],
            },
            {
                'block_id': problem_ai_old,
                'type': 'problem',
                'display_name': 'Quiz cũ: AI Learning Check',
                'parent_block_id': unit_sync,
                'source_ref': f'{problem_ai_old}#old-problem',
                'data': '<problem><multiplechoiceresponse><label>AI-generated question có được publish trực tiếp không?</label><choicegroup><choice correct="true">Không, cần teacher review trước</choice><choice correct="false">Có, luôn publish ngay</choice></choicegroup></multiplechoiceresponse></problem>',
            },
            {
                'block_id': unit_cost,
                'type': 'vertical',
                'display_name': 'Unit 3.2: Cost Control',
                'parent_block_id': seq_ai,
                'children': [html_cost],
                'data': 'Cost Control Layer kiểm soát quota, estimate chi phí và hard stop trước khi gọi GPT API.',
            },
            {
                'block_id': html_cost,
                'type': 'html',
                'display_name': 'Reading: AI Cost Control',
                'parent_block_id': unit_cost,
                'source_ref': f'{html_cost}#html',
                'data': '''
                    <h2>AI Cost Control</h2>
                    <p>Mọi request AI phải đi qua Model Gateway và Cost Control Layer.</p>
                    <p>Hệ thống ước tính input tokens, output tokens, prompt policy, schema và safety factor trước khi gọi model.</p>
                    <p>Quota Phase 1 đề xuất 100-200 câu mỗi course và 20-50 câu mỗi lần generate.</p>
                    <p>Hard stop sẽ chặn job vượt ngân sách hoặc vượt quota để tránh AI chạy thả rông.</p>
                    <p>Usage log ghi lại model, input tokens, output tokens, cost USD/VND và người gọi.</p>
                ''',
                'assets': [
                    {
                        'asset_id': f'{course_id}/assets/cost-control-handout.txt',
                        'file_name': 'AI_Cost_Control_Handout.txt',
                        'mime_type': 'text/plain',
                        'text': 'Cost estimate = input cost + output cost nhân safety factor. Hard stop chặn job vượt quota. Usage log dùng để dashboard chi phí theo course, teacher, feature và model.',
                    }
                ],
            },
        ]



    async def ensure_problem_library(self, course_id: str, chapter_node_id: str, display_name: str, metadata: dict | None = None) -> dict:
        metadata = metadata or {}
        library_key = metadata.get('library_key') or f'{course_id}:{chapter_node_id}'
        tag_names = metadata.get('tag_names') or metadata.get('tags') or []
        return {
            'mode': 'mock',
            'course_id': course_id,
            'chapter_node_id': chapter_node_id,
            'library_key': library_key,
            'openedx_library_id': f'mock-library-{abs(hash(library_key)) % 100000}',
            'display_name': display_name,
            'created': False,
            'status': 'library_ready_mock_existing_or_created',
            'tag_names': tag_names,
            'metadata': metadata,
        }

    async def import_problem_to_library(self, course_id: str, library_key: str, olx: str, display_name: str, metadata: dict | None = None) -> dict:
        metadata = metadata or {}
        tag_names = metadata.get('tag_names') or metadata.get('tags') or []
        return {
            'mode': 'mock',
            'course_id': course_id,
            'library_key': library_key,
            'openedx_library_problem_id': f'mock-library-problem-{abs(hash(display_name + library_key)) % 100000}',
            'openedx_block_id': f'mock-bank-item-{abs(hash(display_name)) % 100000}',
            'display_name': display_name,
            'tag_names': tag_names,
            'metadata': metadata,
            'status': 'imported_to_chapter_library_mock',
        }
    async def verify_library_problem(self, course_id: str, library_key: str, problem_id: str, metadata: dict | None = None) -> dict:
        return {'mode': 'mock', 'ok': True, 'verified': True, 'status': 'mock_verified', 'library_exists': True, 'problem_exists': True, 'published': True, 'has_unpublished_changes': False, 'tag_count': len((metadata or {}).get('tag_names') or []), 'problem_id': problem_id}

    async def delete_library_problem(self, course_id: str, library_key: str, problem_id: str, metadata: dict | None = None) -> dict:
        return {'mode': 'mock', 'ok': True, 'deleted': True, 'status': 'mock_deleted', 'problem_id': problem_id}

    async def publish_problem_olx(self, course_id: str, parent_block_id: str | None, olx: str, display_name: str) -> dict:
        return {
            'mode': 'mock',
            'course_id': course_id,
            'parent_block_id': parent_block_id,
            'openedx_block_id': f'mock-openedx-problem-{abs(hash(display_name)) % 100000}',
            'display_name': display_name,
            'status': 'published_mock',
        }
