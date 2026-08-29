from pathlib import Path


def test_0051_down_revision_matches_real_0050_revision():
    root = Path(__file__).resolve().parents[2]
    vdir = root / "alembic" / "versions"
    migration_0050 = (vdir / "0050_v25_9_16_7_2_12_class_scope_identity.py").read_text(encoding="utf-8")
    migration_0051 = (vdir / "0051_v25_9_16_7_2_21_bulk_academic_jobs.py").read_text(encoding="utf-8")

    assert "revision = '0050_v25_9_16_7_2_12_class_scope'" in migration_0050
    assert "down_revision = '0050_v25_9_16_7_2_12_class_scope'" in migration_0051
    assert "down_revision = '0050_v25_9_16_7_2_12'" not in migration_0051
