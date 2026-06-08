"""v25.9.15.0 versioned question bank first architecture

Revision ID: 0009_v25_9_15_0
Revises: 0008_v25_9_14_5
Create Date: 2026-06-05

Adds department/subject/chapter/bank-version/release tables. A bank release is
immutable enough for production usage and maps 1:1 to one Open edX Content
Library so old courses are not affected when materials change.
"""
from alembic import op
import sqlalchemy as sa

revision = '0009_v25_9_15_0'
down_revision = '0008_v25_9_14_5'
branch_labels = None
depends_on = None


def _table_exists(bind, name: str) -> bool:
    return name in sa.inspect(bind).get_table_names()


def _column_exists(bind, table: str, column: str) -> bool:
    if table not in sa.inspect(bind).get_table_names():
        return False
    return column in {item['name'] for item in sa.inspect(bind).get_columns(table)}


def _create_index_if_missing(bind, name: str, table: str, columns: list[str], unique: bool = False) -> None:
    existing = {item['name'] for item in sa.inspect(bind).get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, 'ai_departments'):
        op.create_table(
            'ai_departments',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('code', sa.String(length=64), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('description', sa.Text(), nullable=False, server_default=''),
            sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('code', name='uq_ai_departments_code'),
        )
        op.create_index('ix_ai_departments_code', 'ai_departments', ['code'])
        op.create_index('ix_ai_departments_status', 'ai_departments', ['status'])

    if not _table_exists(bind, 'ai_subjects'):
        op.create_table(
            'ai_subjects',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('department_id', sa.String(), sa.ForeignKey('ai_departments.id'), nullable=False),
            sa.Column('code', sa.String(length=64), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('description', sa.Text(), nullable=False, server_default=''),
            sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('department_id', 'code', name='uq_ai_subject_department_code'),
        )
        op.create_index('ix_ai_subjects_department_id', 'ai_subjects', ['department_id'])
        op.create_index('ix_ai_subjects_code', 'ai_subjects', ['code'])
        op.create_index('ix_ai_subjects_department_status', 'ai_subjects', ['department_id', 'status'])

    if not _table_exists(bind, 'ai_subject_chapters'):
        op.create_table(
            'ai_subject_chapters',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('subject_id', sa.String(), sa.ForeignKey('ai_subjects.id'), nullable=False),
            sa.Column('chapter_no', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('title', sa.String(length=255), nullable=False),
            sa.Column('description', sa.Text(), nullable=False, server_default=''),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('subject_id', 'chapter_no', name='uq_ai_subject_chapter_no'),
        )
        op.create_index('ix_ai_subject_chapters_subject_id', 'ai_subject_chapters', ['subject_id'])
        op.create_index('ix_ai_subject_chapters_subject_status', 'ai_subject_chapters', ['subject_id', 'status'])

    if not _table_exists(bind, 'ai_question_bank_versions'):
        op.create_table(
            'ai_question_bank_versions',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('subject_id', sa.String(), sa.ForeignKey('ai_subjects.id'), nullable=False),
            sa.Column('chapter_id', sa.String(), sa.ForeignKey('ai_subject_chapters.id'), nullable=False),
            sa.Column('version_no', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('version_code', sa.String(length=64), nullable=False, server_default='v1.0'),
            sa.Column('title', sa.String(length=255), nullable=False, server_default=''),
            sa.Column('change_note', sa.Text(), nullable=False, server_default=''),
            sa.Column('status', sa.String(length=50), nullable=False, server_default='draft'),
            sa.Column('based_on_version_id', sa.String(), sa.ForeignKey('ai_question_bank_versions.id'), nullable=True),
            sa.Column('created_by', sa.String(length=255), nullable=True),
            sa.Column('approved_by', sa.String(length=255), nullable=True),
            sa.Column('published_at', sa.DateTime(), nullable=True),
            sa.Column('metadata_json', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('subject_id', 'chapter_id', 'version_code', name='uq_ai_bank_version_code'),
        )
        op.create_index('ix_ai_question_bank_versions_subject_id', 'ai_question_bank_versions', ['subject_id'])
        op.create_index('ix_ai_question_bank_versions_chapter_id', 'ai_question_bank_versions', ['chapter_id'])
        op.create_index('ix_ai_bank_versions_chapter_status', 'ai_question_bank_versions', ['chapter_id', 'status'])
        op.create_index('ix_ai_question_bank_versions_based_on_version_id', 'ai_question_bank_versions', ['based_on_version_id'])

    if not _table_exists(bind, 'ai_learning_material_versions'):
        op.create_table(
            'ai_learning_material_versions',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('subject_id', sa.String(), sa.ForeignKey('ai_subjects.id'), nullable=False),
            sa.Column('chapter_id', sa.String(), sa.ForeignKey('ai_subject_chapters.id'), nullable=False),
            sa.Column('bank_version_id', sa.String(), sa.ForeignKey('ai_question_bank_versions.id'), nullable=False),
            sa.Column('title', sa.String(length=255), nullable=False, server_default=''),
            sa.Column('file_name', sa.String(length=512), nullable=False, server_default=''),
            sa.Column('file_type', sa.String(length=100), nullable=False, server_default='unknown'),
            sa.Column('storage_path', sa.String(length=1024), nullable=False, server_default=''),
            sa.Column('content_hash', sa.String(length=128), nullable=True),
            sa.Column('version_no', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('change_type', sa.String(length=50), nullable=False, server_default='initial'),
            sa.Column('uploaded_by', sa.String(length=255), nullable=True),
            sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
        )
        op.create_index('ix_ai_learning_material_versions_subject_id', 'ai_learning_material_versions', ['subject_id'])
        op.create_index('ix_ai_learning_material_versions_chapter_id', 'ai_learning_material_versions', ['chapter_id'])
        op.create_index('ix_ai_learning_material_versions_bank_version_id', 'ai_learning_material_versions', ['bank_version_id'])
        op.create_index('ix_ai_material_versions_bank_hash', 'ai_learning_material_versions', ['bank_version_id', 'content_hash'])

    if not _table_exists(bind, 'ai_concept_versions'):
        op.create_table(
            'ai_concept_versions',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('bank_version_id', sa.String(), sa.ForeignKey('ai_question_bank_versions.id'), nullable=False),
            sa.Column('subject_id', sa.String(), sa.ForeignKey('ai_subjects.id'), nullable=False),
            sa.Column('chapter_id', sa.String(), sa.ForeignKey('ai_subject_chapters.id'), nullable=False),
            sa.Column('material_version_id', sa.String(), sa.ForeignKey('ai_learning_material_versions.id'), nullable=True),
            sa.Column('concept_key', sa.String(length=255), nullable=False),
            sa.Column('concept_title', sa.String(length=512), nullable=False),
            sa.Column('description', sa.Text(), nullable=False, server_default=''),
            sa.Column('learning_objective', sa.Text(), nullable=False, server_default=''),
            sa.Column('source_evidence', sa.Text(), nullable=False, server_default=''),
            sa.Column('source_chunk_hash', sa.String(length=128), nullable=True),
            sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('bank_version_id', 'concept_key', name='uq_ai_concept_version_key'),
        )
        op.create_index('ix_ai_concept_versions_bank_version_id', 'ai_concept_versions', ['bank_version_id'])
        op.create_index('ix_ai_concept_versions_subject_id', 'ai_concept_versions', ['subject_id'])
        op.create_index('ix_ai_concept_versions_chapter_id', 'ai_concept_versions', ['chapter_id'])
        op.create_index('ix_ai_concept_versions_material_version_id', 'ai_concept_versions', ['material_version_id'])
        op.create_index('ix_ai_concept_versions_concept_key', 'ai_concept_versions', ['concept_key'])
        op.create_index('ix_ai_concept_versions_source_chunk_hash', 'ai_concept_versions', ['source_chunk_hash'])
        op.create_index('ix_ai_concept_versions_bank_status', 'ai_concept_versions', ['bank_version_id', 'status'])

    if not _table_exists(bind, 'ai_bank_question_families'):
        op.create_table(
            'ai_bank_question_families',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('bank_version_id', sa.String(), sa.ForeignKey('ai_question_bank_versions.id'), nullable=False),
            sa.Column('subject_id', sa.String(), sa.ForeignKey('ai_subjects.id'), nullable=False),
            sa.Column('chapter_id', sa.String(), sa.ForeignKey('ai_subject_chapters.id'), nullable=False),
            sa.Column('concept_version_id', sa.String(), sa.ForeignKey('ai_concept_versions.id'), nullable=True),
            sa.Column('difficulty', sa.String(length=50), nullable=False, server_default='easy'),
            sa.Column('family_key', sa.String(length=255), nullable=False),
            sa.Column('family_title', sa.String(length=512), nullable=False, server_default=''),
            sa.Column('family_fingerprint', sa.String(length=128), nullable=True),
            sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('bank_version_id', 'difficulty', 'family_key', name='uq_ai_bank_family_key'),
        )
        op.create_index('ix_ai_bank_question_families_bank_version_id', 'ai_bank_question_families', ['bank_version_id'])
        op.create_index('ix_ai_bank_question_families_subject_id', 'ai_bank_question_families', ['subject_id'])
        op.create_index('ix_ai_bank_question_families_chapter_id', 'ai_bank_question_families', ['chapter_id'])
        op.create_index('ix_ai_bank_question_families_concept_version_id', 'ai_bank_question_families', ['concept_version_id'])
        op.create_index('ix_ai_bank_question_families_family_key', 'ai_bank_question_families', ['family_key'])
        op.create_index('ix_ai_bank_question_families_family_fingerprint', 'ai_bank_question_families', ['family_fingerprint'])
        op.create_index('ix_ai_bank_families_bank_difficulty_status', 'ai_bank_question_families', ['bank_version_id', 'difficulty', 'status'])

    if not _table_exists(bind, 'ai_question_bank_releases'):
        op.create_table(
            'ai_question_bank_releases',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('bank_version_id', sa.String(), sa.ForeignKey('ai_question_bank_versions.id'), nullable=False),
            sa.Column('subject_id', sa.String(), sa.ForeignKey('ai_subjects.id'), nullable=False),
            sa.Column('chapter_id', sa.String(), sa.ForeignKey('ai_subject_chapters.id'), nullable=False),
            sa.Column('release_code', sa.String(length=128), nullable=False),
            sa.Column('title', sa.String(length=255), nullable=False, server_default=''),
            sa.Column('status', sa.String(length=50), nullable=False, server_default='draft'),
            sa.Column('approved_question_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('easy_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('medium_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('hard_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('family_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('openedx_library_key', sa.String(length=512), nullable=True),
            sa.Column('openedx_library_version', sa.Integer(), nullable=True),
            sa.Column('publish_batch_id', sa.String(), nullable=True),
            sa.Column('published_at', sa.DateTime(), nullable=True),
            sa.Column('published_by', sa.String(length=255), nullable=True),
            sa.Column('metadata_json', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('bank_version_id', 'release_code', name='uq_ai_bank_release_code'),
            sa.UniqueConstraint('openedx_library_key', name='uq_ai_bank_release_openedx_library_key'),
        )
        op.create_index('ix_ai_question_bank_releases_bank_version_id', 'ai_question_bank_releases', ['bank_version_id'])
        op.create_index('ix_ai_question_bank_releases_subject_id', 'ai_question_bank_releases', ['subject_id'])
        op.create_index('ix_ai_question_bank_releases_chapter_id', 'ai_question_bank_releases', ['chapter_id'])
        op.create_index('ix_ai_question_bank_releases_release_code', 'ai_question_bank_releases', ['release_code'])
        op.create_index('ix_ai_question_bank_releases_openedx_library_key', 'ai_question_bank_releases', ['openedx_library_key'])
        op.create_index('ix_ai_bank_releases_chapter_status', 'ai_question_bank_releases', ['chapter_id', 'status'])

    if not _table_exists(bind, 'ai_bank_release_questions'):
        op.create_table(
            'ai_bank_release_questions',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('bank_release_id', sa.String(), sa.ForeignKey('ai_question_bank_releases.id'), nullable=False),
            sa.Column('question_id', sa.String(), sa.ForeignKey('ai_questions.id'), nullable=False),
            sa.Column('question_family_id', sa.String(length=255), nullable=True),
            sa.Column('difficulty', sa.String(length=50), nullable=False, server_default='easy'),
            sa.Column('openedx_library_problem_id', sa.String(length=512), nullable=True),
            sa.Column('included_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('bank_release_id', 'question_id', name='uq_ai_release_question'),
            sa.UniqueConstraint('bank_release_id', 'openedx_library_problem_id', name='uq_ai_release_openedx_problem'),
        )
        op.create_index('ix_ai_bank_release_questions_bank_release_id', 'ai_bank_release_questions', ['bank_release_id'])
        op.create_index('ix_ai_bank_release_questions_question_id', 'ai_bank_release_questions', ['question_id'])
        op.create_index('ix_ai_bank_release_questions_question_family_id', 'ai_bank_release_questions', ['question_family_id'])
        op.create_index('ix_ai_bank_release_questions_difficulty', 'ai_bank_release_questions', ['difficulty'])
        op.create_index('ix_ai_bank_release_questions_openedx_library_problem_id', 'ai_bank_release_questions', ['openedx_library_problem_id'])
        op.create_index('ix_ai_release_questions_release_family', 'ai_bank_release_questions', ['bank_release_id', 'question_family_id'])

    if not _table_exists(bind, 'ai_edx_course_mappings'):
        op.create_table(
            'ai_edx_course_mappings',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('openedx_course_id', sa.String(length=255), nullable=False),
            sa.Column('department_id', sa.String(), sa.ForeignKey('ai_departments.id'), nullable=True),
            sa.Column('subject_id', sa.String(), sa.ForeignKey('ai_subjects.id'), nullable=False),
            sa.Column('term', sa.String(length=100), nullable=True),
            sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
            sa.Column('created_by', sa.String(length=255), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('openedx_course_id', name='uq_ai_edx_course_mapping_course_id'),
        )
        op.create_index('ix_ai_edx_course_mappings_openedx_course_id', 'ai_edx_course_mappings', ['openedx_course_id'])
        op.create_index('ix_ai_edx_course_mappings_department_id', 'ai_edx_course_mappings', ['department_id'])
        op.create_index('ix_ai_edx_course_mappings_subject_id', 'ai_edx_course_mappings', ['subject_id'])
        op.create_index('ix_ai_edx_course_mappings_term', 'ai_edx_course_mappings', ['term'])
        op.create_index('ix_ai_edx_course_mappings_status', 'ai_edx_course_mappings', ['status'])

    if not _table_exists(bind, 'ai_edx_course_chapter_mappings'):
        op.create_table(
            'ai_edx_course_chapter_mappings',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('course_mapping_id', sa.String(), sa.ForeignKey('ai_edx_course_mappings.id'), nullable=False),
            sa.Column('subject_chapter_id', sa.String(), sa.ForeignKey('ai_subject_chapters.id'), nullable=False),
            sa.Column('bank_release_id', sa.String(), sa.ForeignKey('ai_question_bank_releases.id'), nullable=True),
            sa.Column('openedx_parent_node_id', sa.String(length=512), nullable=True),
            sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('course_mapping_id', 'subject_chapter_id', name='uq_ai_course_chapter_mapping'),
        )
        op.create_index('ix_ai_edx_course_chapter_mappings_course_mapping_id', 'ai_edx_course_chapter_mappings', ['course_mapping_id'])
        op.create_index('ix_ai_edx_course_chapter_mappings_subject_chapter_id', 'ai_edx_course_chapter_mappings', ['subject_chapter_id'])
        op.create_index('ix_ai_edx_course_chapter_mappings_bank_release_id', 'ai_edx_course_chapter_mappings', ['bank_release_id'])
        op.create_index('ix_ai_edx_course_chapter_mappings_openedx_parent_node_id', 'ai_edx_course_chapter_mappings', ['openedx_parent_node_id'])

    if not _table_exists(bind, 'ai_quiz_blueprints'):
        op.create_table(
            'ai_quiz_blueprints',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('subject_id', sa.String(), sa.ForeignKey('ai_subjects.id'), nullable=False),
            sa.Column('chapter_id', sa.String(), sa.ForeignKey('ai_subject_chapters.id'), nullable=False),
            sa.Column('title', sa.String(length=255), nullable=False),
            sa.Column('total_questions', sa.Integer(), nullable=False, server_default='15'),
            sa.Column('difficulty_easy', sa.Integer(), nullable=False, server_default='50'),
            sa.Column('difficulty_medium', sa.Integer(), nullable=False, server_default='30'),
            sa.Column('difficulty_hard', sa.Integer(), nullable=False, server_default='20'),
            sa.Column('max_families_per_bank', sa.Integer(), nullable=False, server_default='2'),
            sa.Column('pick_count_per_slot', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
        )
        op.create_index('ix_ai_quiz_blueprints_subject_id', 'ai_quiz_blueprints', ['subject_id'])
        op.create_index('ix_ai_quiz_blueprints_chapter_id', 'ai_quiz_blueprints', ['chapter_id'])
        op.create_index('ix_ai_quiz_blueprints_chapter_status', 'ai_quiz_blueprints', ['chapter_id', 'status'])

    if not _table_exists(bind, 'ai_course_quiz_instances'):
        op.create_table(
            'ai_course_quiz_instances',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('openedx_course_id', sa.String(length=255), nullable=False),
            sa.Column('subject_id', sa.String(), sa.ForeignKey('ai_subjects.id'), nullable=False),
            sa.Column('chapter_id', sa.String(), sa.ForeignKey('ai_subject_chapters.id'), nullable=False),
            sa.Column('bank_release_id', sa.String(), sa.ForeignKey('ai_question_bank_releases.id'), nullable=False),
            sa.Column('quiz_blueprint_id', sa.String(), sa.ForeignKey('ai_quiz_blueprints.id'), nullable=True),
            sa.Column('openedx_quiz_node_id', sa.String(length=512), nullable=True),
            sa.Column('openedx_unit_node_id', sa.String(length=512), nullable=True),
            sa.Column('status', sa.String(length=50), nullable=False, server_default='planned'),
            sa.Column('metadata_json', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
        )
        op.create_index('ix_ai_course_quiz_instances_openedx_course_id', 'ai_course_quiz_instances', ['openedx_course_id'])
        op.create_index('ix_ai_course_quiz_instances_subject_id', 'ai_course_quiz_instances', ['subject_id'])
        op.create_index('ix_ai_course_quiz_instances_chapter_id', 'ai_course_quiz_instances', ['chapter_id'])
        op.create_index('ix_ai_course_quiz_instances_bank_release_id', 'ai_course_quiz_instances', ['bank_release_id'])
        op.create_index('ix_ai_course_quiz_instances_quiz_blueprint_id', 'ai_course_quiz_instances', ['quiz_blueprint_id'])
        op.create_index('ix_ai_course_quiz_instances_openedx_quiz_node_id', 'ai_course_quiz_instances', ['openedx_quiz_node_id'])
        op.create_index('ix_ai_course_quiz_instances_openedx_unit_node_id', 'ai_course_quiz_instances', ['openedx_unit_node_id'])
        op.create_index('ix_ai_course_quiz_instances_course_chapter', 'ai_course_quiz_instances', ['openedx_course_id', 'chapter_id'])

    question_columns = {
        'source_course_id': sa.Column('source_course_id', sa.String(length=255), nullable=True),
        'department_id': sa.Column('department_id', sa.String(), nullable=True),
        'subject_id': sa.Column('subject_id', sa.String(), nullable=True),
        'subject_chapter_id': sa.Column('subject_chapter_id', sa.String(), nullable=True),
        'bank_version_id': sa.Column('bank_version_id', sa.String(), nullable=True),
        'bank_release_id': sa.Column('bank_release_id', sa.String(), nullable=True),
        'material_version_id': sa.Column('material_version_id', sa.String(), nullable=True),
        'concept_version_id': sa.Column('concept_version_id', sa.String(), nullable=True),
    }
    for name, column in question_columns.items():
        if not _column_exists(bind, 'ai_questions', name):
            op.add_column('ai_questions', column)

    for index_name, columns in {
        'ix_ai_questions_source_course_id': ['source_course_id'],
        'ix_ai_questions_department_id': ['department_id'],
        'ix_ai_questions_subject_id': ['subject_id'],
        'ix_ai_questions_subject_chapter_id': ['subject_chapter_id'],
        'ix_ai_questions_bank_version_id': ['bank_version_id'],
        'ix_ai_questions_bank_release_id': ['bank_release_id'],
        'ix_ai_questions_material_version_id': ['material_version_id'],
        'ix_ai_questions_concept_version_id': ['concept_version_id'],
        'ix_ai_questions_bank_version_status': ['bank_version_id', 'status'],
        'ix_ai_questions_subject_chapter_status': ['subject_id', 'subject_chapter_id', 'status'],
        'ix_ai_questions_bank_release_status': ['bank_release_id', 'status'],
    }.items():
        _create_index_if_missing(bind, index_name, 'ai_questions', columns)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        'ai_course_quiz_instances',
        'ai_quiz_blueprints',
        'ai_edx_course_chapter_mappings',
        'ai_edx_course_mappings',
        'ai_bank_release_questions',
        'ai_question_bank_releases',
        'ai_bank_question_families',
        'ai_concept_versions',
        'ai_learning_material_versions',
        'ai_question_bank_versions',
        'ai_subject_chapters',
        'ai_subjects',
        'ai_departments',
    ]:
        if _table_exists(bind, table):
            op.drop_table(table)
    for col in ['concept_version_id', 'material_version_id', 'bank_release_id', 'bank_version_id', 'subject_chapter_id', 'subject_id', 'department_id', 'source_course_id']:
        if _column_exists(bind, 'ai_questions', col):
            op.drop_column('ai_questions', col)
