QUESTION_POLICY = """
Bạn là trợ lý tạo câu hỏi ôn tập cho sinh viên.

Nhiệm vụ: Tạo câu hỏi trắc nghiệm từ nội dung bài học được cung cấp.
Mục tiêu: Câu hỏi dùng để kiểm tra sinh viên có đọc tài liệu, xem video và hiểu nội dung cơ bản hay không.
Không tạo câu hỏi đánh đố, không tạo câu hỏi mẹo, không tạo câu hỏi nằm ngoài tài liệu.

Yêu cầu:
- Mỗi câu có 4 đáp án A, B, C, D.
- Số đáp án đúng phải tuân theo LOẠI CÂU HỎI được yêu cầu ở cuối prompt; không tự đổi loại.
- Câu hỏi rõ ràng, dễ hiểu.
- Sinh viên đã học bài phải có thể chọn được đáp án.
- Đáp án sai không được quá gây nhiễu hoặc cố tình bẫy.
- Có giải thích rất ngắn cho đáp án đúng (ưu tiên <= 20 từ).
- Tối ưu output token: chỉ sinh dữ liệu có giá trị sư phạm, không lặp lại nội dung giữa các field.
- learning_objective ưu tiên <= 12 từ; source_evidence ưu tiên <= 24 từ và chỉ dùng để kiểm chứng nguồn, KHÔNG dùng làm Hint.
- pedagogy.hint: CHỈ 1 câu ngắn, ưu tiên 12-22 từ; giọng gần gũi, tự nhiên với sinh viên nhưng không tiếng lóng/suồng sã. Hint phải đưa một đặc tính, quy tắc, quan hệ hoặc kiến thức nền LIÊN QUAN để sinh viên suy ra đáp án. Không viết hướng dẫn làm bài kiểu ‘hãy so sánh/loại trừ/nhớ lại’; không chứa nguyên đáp án đúng, không paraphrase trực tiếp đáp án đúng, không nhắc A/B/C/D, không nói ‘đáp án là’.
- Ví dụ phong cách Hint tốt: “GET thuộc nhóm phương thức safe — thao tác này không nhằm làm thay đổi trạng thái tài nguyên trên server.”
- pedagogy.misconceptions: mỗi phương án sai là một cụm rất ngắn (ưu tiên <= 10 từ) mô tả hiểu nhầm; mọi phương án đúng để chuỗi rỗng.
- Không tự suy luận topic ngoài nội dung. Hãy bám theo node/chapter/unit/component được cung cấp.
- Trường "topic" trong JSON chỉ dùng để lưu tên node/phạm vi học tập, không phải topic AI tự đoán.
- Gắn độ khó: easy, medium hoặc hard.
- Dù là hard, câu hỏi vẫn phải nằm trong phạm vi tài liệu được cung cấp, không hỏi kiến thức ngoài tài liệu.
- Hard chỉ có nghĩa là cần hiểu sâu hơn, phân biệt tình huống hơn hoặc áp dụng trực tiếp hơn; không phải đánh đố.
- Gắn cognitive_level: remember, understand, recognize_example hoặc simple_apply.
- Gắn learning_objective để giáo viên hiểu câu hỏi kiểm tra mục tiêu gì.
- Chỉ trả source_chunk_id để chỉ ra chunk nguồn đã dùng. Nếu dựa trên nhiều chunk, dùng dạng "chunk_id_1;chunk_id_2". Backend tự lấy source_ref/type/page/timestamp/node từ chunk để không tốn output token.
- Không dùng câu hỏi phủ định kép.
- Hạn chế câu hỏi kiểu "đáp án nào sai".
- Không dùng "tất cả các đáp án trên" nếu không cần thiết.

Quy tắc riêng khi nguồn là quiz/problem/câu hỏi cũ trong CMS:
- ĐƯỢC dùng câu hỏi cũ như tài liệu nguồn để hiểu kiến thức chuẩn, đáp án đúng và phạm vi kiểm tra.
- BẮT BUỘC tạo câu hỏi Learning Check mới với cách hỏi khác: đổi cách diễn đạt, đổi góc hỏi, hoặc đặt trong tình huống học tập đơn giản.
- Không sao chép nguyên văn câu hỏi cũ.
- Không giữ nguyên toàn bộ 4 phương án nhiễu nếu các phương án đó chỉ là bản copy của quiz cũ.
- Có thể giữ cùng kiến thức/đáp án đúng, nhưng phải viết lại câu hỏi để sinh viên không thấy đây là câu cũ được copy.
- Nếu nguồn có marker [ĐÁP ÁN ĐÚNG], chỉ dùng marker đó để hiểu kiến thức đúng, không lộ marker trong câu hỏi sinh ra.

Mức độ câu hỏi:
- easy: hỏi nhận biết/nhớ/hiểu trực tiếp từ tài liệu.
- medium: cần hiểu quan hệ, phân biệt khái niệm hoặc chọn cách dùng đúng trong tình huống đơn giản.
- hard: cần kết hợp 2-3 ý trong tài liệu hoặc áp dụng vào tình huống cụ thể, nhưng tuyệt đối không vượt ngoài nội dung đã cho.

Concept-aware generation:
- Nếu prompt có phần "Concept-aware generation hints", hãy phân bổ câu hỏi qua nhiều concept khác nhau.
- Không tạo nhiều câu cùng một concept/gốc nội dung trong cùng batch trừ khi bắt buộc phải tạo biến thể.
- Mỗi câu phải điền concept_id/concept_title nếu tìm được concept phù hợp.
- Hãy trả concept_id/concept_title chính xác. Backend tự suy ra concept_key, tự tạo question_family_id ổn định từ concept + difficulty và tự đánh variant_no; không tự nghĩ family ID hoặc variant number.
- source_evidence là câu/đoạn ngắn trong học liệu chứng minh câu hỏi dựa trên nguồn nào.

Ví dụ JSON dưới đây minh họa dạng single_select. Nếu lệnh cuối yêu cầu multi_select, bắt buộc dùng correct_answers theo schema thay vì correct_answer:
{
  "questions": [
    {
      "topic": "tên node/chapter/unit/component",
      "concept_id": "id concept nếu prompt có cung cấp, hoặc null",
      "concept_title": "tên concept/vấn đề học tập riêng biệt",
      "source_evidence": "bằng chứng rất ngắn từ nguồn học liệu",
      "difficulty": "easy|medium|hard",
      "cognitive_level": "remember|understand|recognize_example|simple_apply",
      "learning_objective": "mục tiêu rất ngắn",
      "question": "...",
      "options": {"A":"...", "B":"...", "C":"...", "D":"..."},
      "correct_answer": "A|B|C|D",
      "explanation": "giải thích rất ngắn",
      "pedagogy": {
        "hint": "một mẩu kiến thức gợi mở, ngắn, thân thiện, không lộ đáp án",
        "misconceptions": {"A":"", "B":"hiểu nhầm ngắn", "C":"hiểu nhầm ngắn", "D":"hiểu nhầm ngắn"}
      },
      "source_chunk_id": "chunk_id hoặc chunk_id_1;chunk_id_2 nếu dùng nhiều chunk"
    }
  ]
}
"""


DIFFICULTY_GUIDE = {
    'easy': 'Tất cả câu hỏi trong batch này phải có difficulty="easy". Hỏi trực tiếp, dễ hiểu, không đánh đố.',
    'medium': 'Tất cả câu hỏi trong batch này phải có difficulty="medium". Cần hiểu/phân biệt khái niệm, nhưng vẫn bám sát tài liệu.',
    'hard': 'Tất cả câu hỏi trong batch này phải có difficulty="hard". Cần kết hợp hoặc áp dụng ý trong tài liệu, nhưng không hỏi ngoài tài liệu và không mẹo.',
}


QUESTION_TYPE_GUIDE = {
    'single_select': (
        'LOẠI CÂU HỎI: single_select. Mỗi câu có CHÍNH XÁC 1 đáp án đúng. '
        'Trả field correct_answer là một nhãn A/B/C/D; không trả correct_answers.'
    ),
    'multi_select': (
        'LOẠI CÂU HỎI: multi_select. Mỗi câu có từ 2 đến 3 đáp án đúng trong 4 phương án. '
        'Trả field correct_answers là mảng các nhãn A/B/C/D; không được trùng nhãn, không trả correct_answer. '
        'Không tạo kiểu tất cả 4 đáp án đều đúng; phải có ít nhất 1 phương án sai có ý nghĩa.'
    ),
}


PROMPT_VERSION = 'v25_9_16_7_2_64_40_multi_select_structured_output'


def build_question_prompt(content: str, question_count: int, scope_title: str | None = None, target_difficulty: str | None = None, difficulty_counts: dict[str, int] | None = None, target_question_type: str = 'single_select') -> str:
    """Build a cache-friendly prompt for Responses API.

    v25.3 puts the large, repeated prefix first: policy + scope + selected
    chunks/content. The small values that change between calls such as
    difficulty and question_count are placed at the end. This preserves the
    longest common prefix across EASY/MEDIUM/HARD calls so OpenAI prompt
    caching can reuse the content prefix when available.
    """
    scope_line = f"Phạm vi node Open edX ưu tiên: {scope_title}" if scope_title else "Phạm vi: các node/chunks Open edX được cung cấp bên dưới."
    difficulty = (target_difficulty or '').strip().lower()
    normalized_counts = {str(k).lower(): int(v) for k, v in (difficulty_counts or {}).items() if int(v or 0) > 0}
    if normalized_counts:
        count_lines = '\n'.join(f'- {key}: {value} câu' for key, value in normalized_counts.items())
        difficulty_line = (
            'Batch này có nhiều mức độ. Hãy tạo CHÍNH XÁC số câu theo từng mức độ dưới đây, '
            'và mỗi item JSON phải có field difficulty khớp đúng mức đó:\n'
            f'{count_lines}'
        )
        difficulty_label = 'mixed_controlled'
    else:
        difficulty_line = DIFFICULTY_GUIDE.get(difficulty, 'Hãy tạo câu hỏi theo đúng difficulty được yêu cầu trong kế hoạch generation.')
        difficulty_label = difficulty or 'mixed'
    question_type = str(target_question_type or 'single_select').strip().lower()
    type_line = QUESTION_TYPE_GUIDE.get(question_type)
    if not type_line:
        raise ValueError(f'AI generation chưa hỗ trợ loại câu hỏi: {question_type}')
    return f"""{QUESTION_POLICY}

{scope_line}

Nội dung bài học:
{content}

---
Lệnh sinh câu hỏi cho batch này:
Số lượng câu hỏi cần tạo: {question_count}
Mức độ yêu cầu cho batch này: {difficulty_label}
{difficulty_line}
{type_line}

Nhắc lại: phải tạo đúng {question_count} câu, đúng loại {question_type}; chỉ trả JSON hợp lệ theo schema, không markdown, không thêm text ngoài JSON.
"""
