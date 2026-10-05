import re
from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text


def test_release_readiness_accepts_new_head_and_rejects_unmigrated_database(monkeypatch):
    from app.api.routes import health
    root = Path(__file__).resolve().parents[3]
    head = ScriptDirectory(str(root / 'backend/alembic')).get_current_head()
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(255))'))
        connection.execute(text('INSERT INTO alembic_version VALUES (:head)'), {'head': head})
    monkeypatch.setattr(health, 'engine', engine)
    # Exercise the real revision check independently of existing bank columns.
    monkeypatch.setattr(health, '_CORE_SCHEMA_REQUIREMENTS', {})
    assert health._database_schema_state()['ready'] is True
    with engine.begin() as connection:
        connection.execute(text('UPDATE alembic_version SET version_num = :old'),
                           {'old': '0071_analytics_hotpath_identity_indexes'})
    assert health._database_schema_state()['migration_ready'] is False
    for relative in ('scripts/uat-build-gate.sh', 'scripts/claude-code-review-pack.sh',
                     'scripts/question-bank-data-health.py'):
        source = (root / relative).read_text()
        value = re.search(r"EXPECTED_ALEMBIC_(?:HEAD|REVISION)\s*=\s*'([^']+)'", source)
        assert value.group(1) == head, relative
