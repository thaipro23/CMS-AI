from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EXPECTED_HEAD = '0065_academic_job_batch_recovery'


def _python_constant(relative_path: str, name: str) -> object:
    tree = ast.parse((ROOT / relative_path).read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f'{name} is missing from {relative_path}')


def _migration_heads() -> set[str]:
    revisions: dict[str, str | tuple[str, ...] | None] = {}
    for path in (ROOT / 'backend/alembic/versions').glob('*.py'):
        revision = str(_python_constant(str(path.relative_to(ROOT)), 'revision'))
        down_revision = _python_constant(str(path.relative_to(ROOT)), 'down_revision')
        revisions[revision] = down_revision

    referenced: set[str] = set()
    for down_revision in revisions.values():
        if isinstance(down_revision, str):
            referenced.add(down_revision)
        elif isinstance(down_revision, tuple):
            referenced.update(down_revision)
    return set(revisions) - referenced


class CurrentAlembicHeadContractTest(unittest.TestCase):
    def test_operational_consumers_use_the_only_migration_head(self) -> None:
        self.assertEqual(_migration_heads(), {EXPECTED_HEAD})
        self.assertEqual(
            _python_constant('backend/app/api/routes/health.py', '_EXPECTED_ALEMBIC_REVISION'),
            EXPECTED_HEAD,
        )
        self.assertEqual(
            _python_constant('scripts/question-bank-data-health.py', 'EXPECTED_ALEMBIC_REVISION'),
            EXPECTED_HEAD,
        )

        for relative_path in ('scripts/uat-build-gate.sh', 'scripts/claude-code-review-pack.sh'):
            source = (ROOT / relative_path).read_text(encoding='utf-8')
            match = re.search(r"^EXPECTED_ALEMBIC_HEAD='([^']+)'$", source, re.MULTILINE)
            self.assertIsNotNone(match, relative_path)
            self.assertEqual(match.group(1), EXPECTED_HEAD, relative_path)


if __name__ == '__main__':
    unittest.main()
