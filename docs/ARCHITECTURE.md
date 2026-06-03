# Architecture

```text
Open edX Studio/LMS
      |
      | Course Content Connector (Django plugin/API bridge)
      v
FastAPI AI Learning Server
      |
      | Cost Control Layer -> quota, estimate, hard stop, usage log
      | Model Gateway -> GPT-5 mini / local OpenAI-compatible model
      | Celery Queue -> sync, parse, generate, quality check
      v
PostgreSQL + pgvector / Redis / MinIO
```

## Core data structures

- Course Content Tree: model Open edX course as course -> section -> unit -> component.
- HashMap<block_id, content_hash>: detect changed content and skip unchanged blocks.
- ContentChunk list: chunk text/transcript/slides with source references.
- VectorIndex<QuestionEmbedding>: duplicate detection and future RAG.
- PriorityQueue<GenerationJob>: queue generation jobs by priority.
- State Machine: draft_error -> pending_review -> approved/rejected -> published.

## Algorithms

- Course traversal: DFS/BFS, O(N).
- Hash-based change detection: O(N).
- Token-window chunking: O(T).
- Topic quota allocation: O(K log K).
- Duplicate detection: ANN vector search.
- Cost estimation: O(1).
- Budget hard stop: O(1).
