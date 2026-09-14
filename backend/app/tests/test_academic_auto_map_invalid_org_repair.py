from __future__ import annotations

import ast
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'backend/app/services/academic_service.py'


def _load_repair_function():
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    function = next(
        (
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == '_replace_invalid_course_mapping'
        ),
        None,
    )
    if function is None:
        raise AssertionError('_replace_invalid_course_mapping is missing')
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {'Any': object}
    exec(compile(module, str(SOURCE), 'exec'), namespace)
    return namespace['_replace_invalid_course_mapping']


class AcademicAutoMapInvalidOrgRepairTest(unittest.TestCase):
    def test_safe_repair_preserves_previous_mapping_evidence(self):
        previous_validation = {'checks': [{'code': 'org_match', 'status': 'fail'}]}
        mapping = SimpleNamespace(
            openedx_course_id='course-v1:FPL+MAR2023+FA26',
            openedx_course_title='Legacy wrong org',
            validation_status='invalid_org_match',
            validation_json=previous_validation,
            validated_at=None,
            updated_by='old-admin',
            updated_at=None,
            note='legacy mapping',
            active=True,
        )
        now = datetime(2026, 9, 14, 3, 0, 0)

        result = _load_repair_function()(
            mapping,
            candidate='course-v1:FPS+MAR2023+FA26',
            openedx_course_title='Correct course',
            validation={'can_save': True, 'checks': []},
            suggested='course-v1:FPS+MAR2023+FA26',
            candidate_source='cms_openedx_api_exact',
            actor='admin-1',
            now=now,
        )

        self.assertIs(result, mapping)
        self.assertEqual(mapping.openedx_course_id, 'course-v1:FPS+MAR2023+FA26')
        self.assertEqual(mapping.validation_status, 'auto_mapped')
        self.assertEqual(mapping.updated_by, 'admin-1')
        self.assertEqual(mapping.updated_at, now)
        self.assertEqual(
            mapping.validation_json['replaced_invalid_mapping'],
            {
                'openedx_course_id': 'course-v1:FPL+MAR2023+FA26',
                'openedx_course_title': 'Legacy wrong org',
                'validation_status': 'invalid_org_match',
                'validation_json': previous_validation,
                'validated_at': None,
                'updated_by': 'old-admin',
                'updated_at': None,
                'note': 'legacy mapping',
            },
        )


if __name__ == '__main__':
    unittest.main()
