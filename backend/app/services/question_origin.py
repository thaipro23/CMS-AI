from sqlalchemy import and_, exists, func, or_
from sqlalchemy.orm import aliased

from app.models.question import Question

NON_AI_SOURCE_TYPES = ('manual', 'manual_import', 'openedx_import', 'legacy_quiz_excel')


def _direct_ai_generated_predicate(question):
    return and_(
        func.lower(func.coalesce(question.authoring_mode, 'ai')).notin_(['manual', 'import']),
        func.lower(func.coalesce(question.model_provider, 'openai')) != 'manual',
        or_(
            func.lower(func.coalesce(question.source_type, '')).notin_(NON_AI_SOURCE_TYPES),
            # source_type describes the material too: AI can generate new
            # questions from imported legacy quiz chunks. Persisted generation
            # provenance distinguishes those from historical imported rows.
            question.generation_job_id.isnot(None),
            func.lower(func.coalesce(question.source_node_id, '')).like('bank-version:%:material:%'),
        ),
    )


def ai_generated_question_predicate():
    """Exclude imports, including old copies that lost their origin markers."""
    origin = aliased(Question)
    # Old copy paths retained lineage even when they replaced source_type and
    # defaulted authoring_mode to AI. Resolve that origin by indexed primary key
    # inside the same query, without loading each ancestor in Python.
    non_ai_origin = exists().where(
        origin.id == func.coalesce(
            func.nullif(Question.lineage_root_question_id, Question.id),
            Question.previous_question_id,
        ),
        ~_direct_ai_generated_predicate(origin),
    ).correlate(Question)
    copied = or_(
        Question.is_carry_over.is_(True),
        Question.source_type.in_(['bank_carry_over', 'subject_offering_clone']),
    )
    return and_(_direct_ai_generated_predicate(Question), ~and_(copied, non_ai_origin))
