# v25.9.16.7.2.51 — Claude Code Review Readiness Pack

## Mục tiêu

Bản `.51` không mở rộng nghiệp vụ mới. Mục tiêu là đóng gói dự án ở trạng thái dễ kiểm tra bởi reviewer độc lập/Claude AI, có bằng chứng tĩnh rõ ràng và guardrail để review không bị mơ hồ.

## Thay đổi chính

1. Thêm `scripts/claude-code-review-pack.sh`.
2. Script sinh gói review gồm manifest SHA256, summary pass/warn/fail, danh sách route, danh sách test versioned, danh sách source frontend.
3. Guardrail tĩnh:
   - đồng bộ version `.51` trong các file trọng yếu;
   - migration latest vẫn là `0052_v25_9_16_7_2_27_learning_behavior_logic_calibration.py`;
   - không có wording cứng “gian lận/cheating/vi phạm chắc chắn” trong source;
   - rà lệnh phá dữ liệu trong scripts/source;
   - rà route API có tham chiếu raw `tracking.log`;
   - `python -m compileall backend/app`;
   - `bash -n` cho release helper scripts.
4. Thêm `docs/CLAUDE_CODE_REVIEW_HANDOFF_V25_9_16_7_2_51.md` để người review biết điểm cần soi.
5. Thêm test static `.51` để bắt stale version và đảm bảo review pack tồn tại.

## Không thay đổi

- Không migration mới.
- Không đổi thuật toán learning behavior.
- Không đổi luồng RollNumber `.40`.
- Không đổi cleanup UAT `.45`.
- Không đổi Bank/Analytics behavior trước đó.
- Không thêm job mới.
- Không mutate dữ liệu.

## Chạy review pack

```bash
cd /opt/ai-server
OUT_DIR=/tmp/ai-server-claude-review-$(date +%Y%m%d-%H%M%S) \
./scripts/claude-code-review-pack.sh
```

Kết quả quan trọng:

```text
review-summary.json
CLAUDE_REVIEW_BRIEF.md
file-manifest.json
banned-wording-source.txt
dangerous-commands.txt
routes-raw-trackinglog.txt
backend-routes.txt
versioned-tests.txt
frontend-source-files.txt
```

## Ý nghĩa cảnh báo

Một số cảnh báo có thể là false-positive nhưng vẫn nên để reviewer nhìn thấy. Ví dụ script có thể cảnh báo khi thấy lệnh phá dữ liệu trong tài liệu UAT hoặc helper có guard. Không được tự động bỏ qua; cần đọc file output tương ứng.
