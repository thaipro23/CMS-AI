from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding='utf-8')


def test_training_class_index_starts_with_term_branch_campus_and_matches_normalized_filters() -> None:
    migration = read('backend/alembic/versions/0062_v25_9_16_7_2_64_40_training_scope_indexes.py')
    assert "'term_id'" in migration
    assert "sa.text('lower(branch)')" in migration
    assert "sa.text('lower(campus)')" in migration
    assert "'subject_id'" in migration
    assert "'class_code'" in migration
    assert "postgresql_where=sa.text('active IS TRUE')" in migration


def test_training_delivery_index_matches_normalized_term_branch_platform_join() -> None:
    migration = read('backend/alembic/versions/0062_v25_9_16_7_2_64_40_training_scope_indexes.py')
    assert "sa.text(\"lower(coalesce(branch, 'poly'))\")" in migration
    assert "'learning_platform'" in migration
    assert "'subject_id'" in migration
    assert "'block_id'" in migration


def test_postgres_training_indexes_are_built_concurrently() -> None:
    migration = read('backend/alembic/versions/0062_v25_9_16_7_2_64_40_training_scope_indexes.py')
    assert "if bind.dialect.name == 'postgresql':" in migration
    assert 'with op.get_context().autocommit_block()' in migration
    assert '_create_indexes(concurrent=True)' in migration
    assert 'postgresql_concurrently=concurrent' in migration
