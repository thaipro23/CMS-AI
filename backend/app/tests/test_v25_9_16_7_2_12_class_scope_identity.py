from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_ap_class_resolver_uses_full_operating_scope():
    service = (ROOT / 'app' / 'services' / 'ap_academic_sync.py').read_text(encoding='utf-8')

    assert 'campus: str | None,' in service
    assert 'branch: str,' in service
    assert 'AcademicClass.campus == target_campus' in service
    assert 'AcademicClass.branch == target_branch' in service
    assert 'same class_code in another campus is valid' in service
    assert 'campus=campus,' in service
    assert 'branch=branch,' in service


def test_academic_class_model_no_longer_uses_class_code_without_campus_scope():
    model = (ROOT / 'app' / 'models' / 'academic.py').read_text(encoding='utf-8')

    assert 'uq_academic_classes_term_block_subject_code' not in model
    assert 'uq_academic_classes_active_scope_code' in model
    assert "'term_id', 'block_id', 'subject_id', 'class_code', 'campus', 'branch'" in model
    assert "postgresql_where=text('active IS TRUE')" in model


def test_alembic_migration_drops_old_class_unique_constraint_and_adds_scope_index():
    migration = (ROOT / 'alembic' / 'versions' / '0050_v25_9_16_7_2_12_class_scope_identity.py').read_text(encoding='utf-8')

    assert "down_revision = '0049_v25_9_16_6_3'" in migration
    assert 'DROP CONSTRAINT IF EXISTS uq_academic_classes_term_block_subject_code' in migration
    assert 'CREATE UNIQUE INDEX IF NOT EXISTS uq_academic_classes_active_scope_code' in migration
    assert "COALESCE(campus, '')" in migration
    assert "COALESCE(branch, '')" in migration
    assert 'WHERE active IS TRUE' in migration
