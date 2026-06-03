# Implementation Plan

## Week 1-2

- Setup repository, Docker Compose, FastAPI, Next.js, PostgreSQL, Redis, MinIO.
- Build basic Course Content Connector interface.
- Build cost estimate API and budget policy tables.

## Week 3-4

- Implement content sync, content hash detection, chunking.
- Implement parsing for HTML/transcript/PDF/PPTX.
- Store chunks with source references.

## Week 5-6

- Implement Model Gateway for GPT-5 mini and mock mode.
- Implement prompt policy and JSON schema output.
- Implement question generation job queue.

## Week 7

- Implement Quality Checker: JSON, anti-trick, source, duplicate placeholder.
- Implement Teacher Review UI.

## Week 8

- Implement Question Bank lifecycle and publish placeholder.
- Demo MVP with 3 real courses.

## Week 9-10

- Fix bugs, improve dashboard, add monitoring metrics, tune prompt/cost estimator.
