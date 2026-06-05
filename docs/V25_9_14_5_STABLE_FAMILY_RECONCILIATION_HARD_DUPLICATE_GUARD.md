# v25.9.14.5 — Stable Family Reconciliation + Deterministic Hard Duplicate Guard

## Quyết định kiến trúc

Concept đã được trích xuất trước và câu hỏi đã được generate với `concept_id`, `concept_key`, `concept_title`. Vì vậy bước lập Family Slot Plan **không gọi GPT/OpenAI lại**.

Nguồn sự thật mới:

```text
stable question_family_id = fam-v1-<hash>-<difficulty>
hash = course_id + chapter_node_id + concept identity + difficulty
```

Thứ tự xác định `concept identity` là `concept_id` → `concept_key` → root family cũ đã bỏ suffix variant → `concept_title` có scope node → fallback nội dung cũ. `variant_no` và question ID tuyệt đối không tham gia công thức. Family cũ chỉ là fallback cho row thiếu liên kết concept; sau khi thành `fam-v1-*`, reconcile chạy lại vẫn giữ nguyên ID.

## Luồng mới

```text
Câu approved/published
→ reconcile stable family ID + variant_no
→ collapse bản ghi/câu trùng chính xác thành canonical identity
→ gom theo stable family
→ bin-pack nguyên family vào slot theo difficulty
→ Hard Duplicate Guard
→ publish Library / tạo Quiz / insert Problem Bank
```

## Bảo đảm

- Một `question_id` không xuất hiện nhiều lần.
- Một Open edX component không xuất hiện nhiều lần.
- Một nội dung câu normalize/fingerprint không xuất hiện nhiều lần.
- Một stable family không bị tách sang nhiều slot.
- Mọi câu duy nhất approved/published trong Chapter được dùng đúng một lần.
- Nếu số family ít hơn số slot yêu cầu, hệ thống giảm số slot; không lặp và không tách family.
- Nếu số family nhiều hơn số slot, nhiều family được đặt chung một slot để tận dụng toàn bộ câu.
- Câu trùng chính xác ở nhiều DB row/component chỉ giữ một canonical question trong plan; dùng tất cả row trùng sẽ làm tăng xác suất và có thể random ra cùng câu.

## Migration

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production exec backend alembic upgrade head
```

Migration `0008_v25_9_14_5_stable_family_reconciliation.py` cập nhật toàn bộ `question_family_id` sang dạng `fam-v1-*`, đánh lại `variant_no` tuần tự và chạy idempotent với index hỗ trợ.

Migration này không đổi schema của component Open edX và không tự publish lại tag. Sau khi cần cập nhật tag Family trên Library cũ, dùng flow replace/backfill-tags đã có.

## Env

```env
APP_VERSION=25.9.14.5-stable-family
FAMILY_PLAN_RECONCILE_ON_PREVIEW=true
FAMILY_PLAN_REQUIRE_ALL_APPROVED=true
FAMILY_PLAN_HARD_DUPLICATE_GUARD=true
```

Không còn dùng các biến `FAMILY_PLAN_AI_*`.

## Kiểm tra SQL sau migration

Các family ID có suffix variant kiểu `-1`, `-2` phải được hợp nhất thành cùng một `fam-v1-*` khi chúng có cùng concept/root family:

```sql
SELECT difficulty, concept_key, question_family_id, COUNT(*) AS variants,
       MIN(variant_no) AS min_variant, MAX(variant_no) AS max_variant
FROM ai_questions
WHERE course_id = 'course-v1:FPT+DOM123+SU26'
GROUP BY difficulty, concept_key, question_family_id
ORDER BY difficulty, concept_key;
```

Kiểm tra mỗi family có variant number liên tục:

```sql
SELECT question_family_id, COUNT(*) AS variants,
       MIN(variant_no) AS min_variant, MAX(variant_no) AS max_variant
FROM ai_questions
WHERE course_id = 'course-v1:FPT+DOM123+SU26'
GROUP BY question_family_id
HAVING MIN(variant_no) <> 1 OR MAX(variant_no) <> COUNT(*);
```

Kết quả mong muốn: `0 rows`.

## API/UI

Endpoint giữ nguyên:

```http
POST /api/publish/courses/{course_id}/family-bank-plan/preview
```

Response mới có:

```json
{
  "planner_engine": "stable_family_deterministic_v1",
  "uses_llm": false,
  "stable_family_count": 12,
  "family_reconciliation": {
    "family_count_before": 18,
    "family_count_after": 12,
    "merged_family_count": 6,
    "updated_question_count": 20,
    "variant_no_updated_count": 14
  },
  "hard_guard": {
    "valid": true
  }
}
```

Nút UI đổi từ `AI tối ưu kế hoạch` thành `Tính kế hoạch tối ưu`.
