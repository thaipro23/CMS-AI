"""chapter module libraries

Revision ID: 0002_chapter_libraries
Revises: 0001_initial_schema
Create Date: 2026-05-08

v25.9.13.46 note:
    0001_initial_schema intentionally uses current SQLAlchemy metadata in this
    legacy project. On a fresh database that means newer tables/columns may
    already exist before this migration runs. Keep this migration idempotent so
    clean rebuilds and older upgraded databases both work.
"""
from alembic import op

revision = '0002_chapter_libraries'
down_revision = '0001_initial_schema'
branch_labels = None
depends_on = None


def upgrade():
    # Idempotent because 0001_initial_schema may already create this table from
    # current SQLAlchemy metadata on a clean database.
    op.execute("""
    CREATE TABLE IF NOT EXISTS ai_course_libraries (
        id VARCHAR PRIMARY KEY,
        course_id VARCHAR(255) NOT NULL,
        chapter_node_id VARCHAR(512) NOT NULL,
        chapter_title VARCHAR(512),
        library_key VARCHAR(512) NOT NULL,
        display_name VARCHAR(512),
        openedx_library_id VARCHAR(512),
        status VARCHAR(50),
        metadata_json JSON,
        created_at TIMESTAMP,
        updated_at TIMESTAMP
    )
    """)

    # Older v24 schema had one library per chapter. Newer models add difficulty
    # in 0003. Do not recreate constraints here if the newer constraint already
    # exists; 0003 will normalize the unique index/constraint.
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'uq_course_chapter_library'
        ) AND NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'uq_course_chapter_difficulty_library'
        ) THEN
            ALTER TABLE ai_course_libraries
            ADD CONSTRAINT uq_course_chapter_library UNIQUE (course_id, chapter_node_id);
        END IF;
    END $$;
    """)

    for statement in [
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS source_node_id VARCHAR(512)",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS source_node_title VARCHAR(512)",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS chapter_node_id VARCHAR(512)",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS chapter_title VARCHAR(512)",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS target_library_id VARCHAR",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS target_library_key VARCHAR(512)",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS openedx_library_problem_id VARCHAR(512)",
        "ALTER TABLE ai_questions ADD COLUMN IF NOT EXISTS imported_library_at TIMESTAMP",
    ]:
        op.execute(statement)


def downgrade():
    # Keep downgrade conservative. Dropping columns/tables from production can
    # destroy publish history, and later migrations depend on these objects.
    pass
