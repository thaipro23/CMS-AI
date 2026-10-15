# CMS-AI / Dash CMS

FastAPI/Celery backend + Next.js frontend cho ngân hàng câu hỏi, nhập Quiz cũ,
vận hành đào tạo AP Poly/PTCĐ và Learning Analytics; kết nối Open edX qua plugin.
Nhánh nghiệp vụ: `feat/import-quiz-cms-old-su26`.

## Đọc nhanh

- [AGENTS.md](AGENTS.md): điểm vào cho AI, quy tắc đọc có scope.
- [CODE_INDEX.md](CODE_INDEX.md): map thư mục và điểm vào theo tác vụ.
- [docs/INDEX.md](docs/INDEX.md): tài liệu hiện hành/lịch sử.
- [docs/CURRENT_STATE.md](docs/CURRENT_STATE.md): snapshot nguồn ngày 15/10/2026;
  commit không đồng nghĩa production đã cập nhật.
- [docs/REPO_INDEX.md](docs/REPO_INDEX.md): tra file từ metadata và kiểm tra độ mới.
- [RUN_CURRENT.md](RUN_CURRENT.md): chọn runbook và kiểm tra triển khai.

```sh
python scripts/repo_index.py check
python scripts/repo_index.py find "quiz" --limit 10
python scripts/repo_index.py ls backend/app/services
```

Phiên bản trong [VERSION](VERSION) là `25.9.16.7.2.64.16.5.7.2.18`;
nhánh có thêm hotfix sau release. Migration nguồn mới nhất được kiểm tra là
[`0073_assessment_average_grade`](backend/alembic/versions/0073_assessment_average_grade.py).
Đối chiếu Alembic graph/database thực tế trước khi chạy migrate.

Feature Quiz SU26: [spec/operations](docs/IMPORT_QUIZ_CMS_OLD_SU26.md).
Release note .18: [question authoring/import/quota](RELEASE_v25.9.16.7.2.64.16.5.7.2.18_QUESTION_AUTHORING_TYPES_OPENEDX_IMPORT_QUIZ_QUOTA.md).
Các file `AI_SERVER_PROJECT_*`, `RUN_V*`, `RELEASE_v*`, `VERIFICATION_v*` là hồ sơ
phiên bản; tra khi cần bằng `find --docs --history`. Không nạp tất cả vào context.
