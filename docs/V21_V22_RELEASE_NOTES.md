# v21-v22 Release Notes

## v21 - Guided Workflow + Review Modal

- Added `/workflow` as the main teacher flow: Sync → Select node/chunks → Estimate → Generate → Review → Export.
- The workflow uses Open edX nodes/chunks directly and does not use guessed topics.
- Added smoother step navigation and direct links to Teacher Review and Export.
- Changed question edit UX from inline panel to popup/modal so teachers can edit without leaving the review context.
- Fixed frontend API base URL handling to support the existing `.env` key: `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`.

## v22 - User Analytics

- Added backend endpoint: `GET /api/users/analytics`.
- Added frontend page: `/users`.
- Added sidebar navigation item: User Analytics.
- Tracks per user:
  - generation jobs
  - requested question count
  - approve/reject/publish actions
  - edits
  - input/output tokens
  - cost USD/VND
  - last activity
- Supports search and sort by cost/job/question/review/edit/token/activity.

## Node-based direction kept

- Topic guessing remains removed from the main workflow.
- Generate and workflow default to synced course chunks.
- Source type is only a chunk filter: `all`, `html`, `transcript`, `problem`, `file`.

## Run

```bat
copy .env.example .env
docker compose up --build
```

Frontend: http://localhost:3000  
Backend docs: http://localhost:8000/docs

If port 8000 is busy, stop the old container/process or change `BACKEND_PORT` and `NEXT_PUBLIC_API_BASE_URL` together.
