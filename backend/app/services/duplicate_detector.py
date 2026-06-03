from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.question import Question, QuestionEmbedding
from app.services.embedding_service import HashEmbeddingService


class DuplicateDetector:
    def __init__(self, db: Session, threshold: float = 0.92):
        self.db = db
        self.threshold = threshold
        self.embedding = HashEmbeddingService()

    def find_duplicate(self, course_id: str, question_text: str) -> tuple[str | None, float]:
        new_vector = self.embedding.embed(question_text)
        rows = self.db.query(QuestionEmbedding).filter(QuestionEmbedding.course_id == course_id).all()
        best_id: str | None = None
        best_score = 0.0
        for row in rows:
            score = self.embedding.cosine(new_vector, row.embedding_vector or [])
            if score > best_score:
                best_id = row.question_id
                best_score = score
        if best_score >= self.threshold:
            return best_id, best_score
        return None, best_score

    def save_embedding(self, question: Question) -> None:
        existing = self.db.query(QuestionEmbedding).filter(QuestionEmbedding.question_id == question.id).first()
        vector = self.embedding.embed(question.question_text)
        if existing:
            existing.embedding_vector = vector
            existing.question_text = question.question_text
            existing.question_hash = question.question_hash
            return
        self.db.add(QuestionEmbedding(
            question_id=question.id,
            course_id=question.course_id,
            topic_id=question.topic_id,
            question_text=question.question_text,
            question_hash=question.question_hash,
            embedding_vector=vector,
        ))
