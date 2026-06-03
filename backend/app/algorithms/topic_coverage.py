from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TopicAllocation:
    topic_id: str
    title: str
    question_quota: int
    importance_score: float


class TopicCoverageAllocator:
    """Allocate questions across topics to avoid topic imbalance."""

    def allocate(self, topics: list[dict], total_questions: int) -> list[TopicAllocation]:
        if total_questions <= 0:
            return []
        if not topics:
            return [TopicAllocation(topic_id="general", title="General", question_quota=total_questions, importance_score=1.0)]

        sorted_topics = sorted(
            topics,
            key=lambda item: (float(item.get("importance_score") or 1), int(item.get("token_count") or 0)),
            reverse=True,
        )
        k = len(sorted_topics)
        base = total_questions // k
        remainder = total_questions % k
        allocations: list[TopicAllocation] = []
        for index, topic in enumerate(sorted_topics):
            quota = base + (1 if index < remainder else 0)
            if quota <= 0:
                continue
            allocations.append(TopicAllocation(
                topic_id=str(topic.get("id") or topic.get("topic_id") or topic.get("title")),
                title=str(topic.get("title") or "General"),
                question_quota=quota,
                importance_score=float(topic.get("importance_score") or 1),
            ))
        return allocations


def create_batches(total_questions: int, batch_size: int = 50) -> list[int]:
    batches: list[int] = []
    remaining = max(0, total_questions)
    while remaining:
        current = min(batch_size, remaining)
        batches.append(current)
        remaining -= current
    return batches
