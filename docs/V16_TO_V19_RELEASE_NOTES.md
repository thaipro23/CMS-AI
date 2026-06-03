# v16-v19 Release Notes

This release moves the project closer to the 10/10 technical plan by turning the core data-structure and algorithm sections into working code.

## v16 — Real Open edX integration readiness

- Improved `RealOpenEdXConnector` normalization for Course Blocks API responses.
- Preserves `children`, `parent_block_id`, `source_ref`, metadata and transcript payloads where available.
- Mock connector now returns a realistic course tree: chapter → sequential → vertical → html/video/problem.
- Course Sync now builds course tree order before extraction.

## v17 — Content extraction pipeline

- Added `ContentExtractor` for HTML, transcript, PDF and PPTX-like asset payloads.
- Added HTML cleaning via BeautifulSoup.
- Added transcript cleanup for SRT/VTT-like timestamps.
- Added PDF/PPTX extraction helpers for connector-provided bytes.
- Course Sync now chunks extracted content with source references, page and timestamp metadata.

## v18 — Course tree + topic coverage algorithms

- Added `CourseTreeBuilder` with DFS traversal.
- Added `TopicService` to extract heuristic topics and assign chunks to topics.
- Added `TopicCoverageAllocator` to distribute question quota across topics.
- Generate API now supports `chunk_ids` and `use_topic_coverage`.
- Worker now supports per-topic generation calls when topic allocation is present.

## v19 — Source grounding + duplicate detection

- Added deterministic hash embedding service as a local/dev embedding layer.
- Added `QuestionEmbedding` model and `DuplicateDetector`.
- Quality checker now supports:
  - anti-trick rules,
  - double-negative detection,
  - answer distinctiveness check,
  - optional source chunk validation,
  - quality flags and quality score.
- Question creation now stores embeddings and flags duplicates.

## UI/UX improvements

- Course Sync page now shows:
  - course tree,
  - extracted topics,
  - chunk browser with topic/source filters,
  - sync metrics.
- Generate page now starts in production-friendly course-chunks mode.
- Generate page includes topic coverage toggle, topic filter, selected token totals and clearer workflow copy.
- Added more friendly hero cards, tree view, topic cards and clearer action flow.

## Notes

The connector is still adapter-based. For `cms.poly.edu.vn`, configure OAuth/service account and set `USE_MOCK_OPENEDX=false`. If Course Blocks API does not expose draft Studio content or assets/transcripts, deploy the included Open edX connector plugin and make `RealOpenEdXConnector` point to that plugin endpoint.
