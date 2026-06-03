from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.token_calibration import TokenCalibration
from app.services.prompt_builder import PROMPT_VERSION

# Conservative defaults based on actual JSON output shape in this project.
# The previous 320 tokens/question was too low for full JSON questions that
# include options, explanation, source grounding and metadata.
DEFAULT_OUTPUT_TOKENS_PER_QUESTION: dict[str, int] = {
    'easy': 650,
    'medium': 750,
    'hard': 900,
    'mixed': 750,
}

MIN_SAFE_OUTPUT_TOKENS_PER_QUESTION = 500
MAX_REASONABLE_OUTPUT_TOKENS_PER_QUESTION = 2000
DEFAULT_QUESTION_TYPE = 'single_choice'


@dataclass
class OutputTokenEstimate:
    difficulty: str
    question_count: int
    tokens_per_question: float
    output_tokens: int
    source: str
    sample_count: int = 0


class OutputTokenCalibrationService:
    """Estimate and learn output tokens/question from actual usage.

    Input token estimates can use /v1/responses/input_tokens before the model
    runs. Output tokens cannot, so this service uses rolling averages from real
    completed/partial jobs. It is scoped by model + course + difficulty + prompt
    version, with a global fallback.
    """

    def __init__(self, db: Session):
        self.db = db

    def estimate_tokens_per_question(
        self,
        *,
        model_name: str,
        course_id: str | None,
        difficulty: str | None,
        question_type: str = DEFAULT_QUESTION_TYPE,
        prompt_version: str = PROMPT_VERSION,
    ) -> tuple[float, str, int]:
        diff = self._normalise_difficulty(difficulty)
        course_key = course_id or 'global'

        # Prefer course-specific calibration.
        row = self._get_row(model_name, course_key, diff, question_type, prompt_version)
        if row and row.sample_count > 0:
            return self._safe(row.avg_output_tokens_per_question), 'calibrated_course', int(row.sample_count or 0)

        # Fall back to global calibration for the same model/difficulty.
        global_row = self._get_row(model_name, 'global', diff, question_type, prompt_version)
        if global_row and global_row.sample_count > 0:
            return self._safe(global_row.avg_output_tokens_per_question), 'calibrated_global', int(global_row.sample_count or 0)

        return float(DEFAULT_OUTPUT_TOKENS_PER_QUESTION.get(diff, DEFAULT_OUTPUT_TOKENS_PER_QUESTION['mixed'])), 'default_safe', 0

    def estimate_output_for_item(
        self,
        *,
        model_name: str,
        course_id: str | None,
        difficulty: str | None,
        question_count: int,
        question_type: str = DEFAULT_QUESTION_TYPE,
        prompt_version: str = PROMPT_VERSION,
    ) -> OutputTokenEstimate:
        tokens_per_question, source, sample_count = self.estimate_tokens_per_question(
            model_name=model_name,
            course_id=course_id,
            difficulty=difficulty,
            question_type=question_type,
            prompt_version=prompt_version,
        )
        count = max(int(question_count or 0), 0)
        return OutputTokenEstimate(
            difficulty=self._normalise_difficulty(difficulty),
            question_count=count,
            tokens_per_question=tokens_per_question,
            output_tokens=int(round(count * tokens_per_question)),
            source=source,
            sample_count=sample_count,
        )

    def update_from_observation(
        self,
        *,
        model_name: str,
        course_id: str | None,
        difficulty: str | None,
        question_count: int,
        output_tokens: int,
        question_type: str = DEFAULT_QUESTION_TYPE,
        prompt_version: str = PROMPT_VERSION,
    ) -> TokenCalibration | None:
        count = int(question_count or 0)
        output = int(output_tokens or 0)
        if count <= 0 or output <= 0:
            return None

        observed = self._safe(output / count)
        diff = self._normalise_difficulty(difficulty)
        course_key = course_id or 'global'

        course_row = self._upsert_row(model_name, course_key, diff, question_type, prompt_version, observed, count, output)
        # Also maintain a model-level global fallback so a new course starts
        # with realistic defaults after the first real jobs have run.
        self._upsert_row(model_name, 'global', diff, question_type, prompt_version, observed, count, output)
        self.db.commit()
        return course_row

    def _get_row(self, model_name: str, course_id: str, difficulty: str, question_type: str, prompt_version: str) -> TokenCalibration | None:
        return self.db.query(TokenCalibration).filter(
            TokenCalibration.model_name == model_name,
            TokenCalibration.course_id == course_id,
            TokenCalibration.difficulty == difficulty,
            TokenCalibration.question_type == question_type,
            TokenCalibration.prompt_version == prompt_version,
        ).first()

    def _upsert_row(
        self,
        model_name: str,
        course_id: str,
        difficulty: str,
        question_type: str,
        prompt_version: str,
        observed_tokens_per_question: float,
        question_count: int,
        output_tokens: int,
    ) -> TokenCalibration:
        row = self._get_row(model_name, course_id, difficulty, question_type, prompt_version)
        if not row:
            row = TokenCalibration(
                model_name=model_name,
                course_id=course_id,
                difficulty=difficulty,
                question_type=question_type,
                prompt_version=prompt_version,
                avg_output_tokens_per_question=observed_tokens_per_question,
                min_output_tokens_per_question=observed_tokens_per_question,
                max_output_tokens_per_question=observed_tokens_per_question,
                sample_count=1,
                last_actual_output_tokens=output_tokens,
                last_question_count=question_count,
                last_observed_tokens_per_question=observed_tokens_per_question,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            self.db.add(row)
            return row

        old_samples = int(row.sample_count or 0)
        # Weighted rolling average by number of questions, so a 20-question job
        # influences calibration more than a 1-question repair.
        old_weight = max(old_samples, 0)
        new_weight = max(int(question_count or 0), 1)
        if old_weight <= 0:
            new_avg = observed_tokens_per_question
        else:
            new_avg = ((float(row.avg_output_tokens_per_question or 0) * old_weight) + (observed_tokens_per_question * new_weight)) / (old_weight + new_weight)
        row.avg_output_tokens_per_question = self._safe(new_avg)
        row.min_output_tokens_per_question = min(float(row.min_output_tokens_per_question or observed_tokens_per_question), observed_tokens_per_question)
        row.max_output_tokens_per_question = max(float(row.max_output_tokens_per_question or observed_tokens_per_question), observed_tokens_per_question)
        row.sample_count = old_samples + new_weight
        row.last_actual_output_tokens = output_tokens
        row.last_question_count = question_count
        row.last_observed_tokens_per_question = observed_tokens_per_question
        row.updated_at = datetime.utcnow()
        self.db.add(row)
        return row

    @staticmethod
    def _normalise_difficulty(difficulty: str | None) -> str:
        diff = (difficulty or 'mixed').strip().lower()
        return diff if diff in {'easy', 'medium', 'hard'} else 'mixed'

    @staticmethod
    def _safe(value: float) -> float:
        return max(MIN_SAFE_OUTPUT_TOKENS_PER_QUESTION, min(float(value or 0), MAX_REASONABLE_OUTPUT_TOKENS_PER_QUESTION))
